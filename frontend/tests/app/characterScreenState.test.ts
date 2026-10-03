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
//   - the submits clear the error first, apply the server's returned row to the
//     workspace characters state, are never optimistic, and on failure set one fixed
//     sentence per action without rejecting.
//
// Feature 018, step 008 — the draft page and blur-save (DoD-1..DoD-11). Expected values
// come from 008.draft-page-state.md (Interface intent, DoD), 008.context.md and the
// feature context.md's D6, D7 and UI strings table. 009's canSubmit / submitSave are out
// of the contract (D6, D7): their tests are replaced by the "018 step 008" describes
// below, and the tests that mixed them in are amended (titles end "— DoD-11").
import { isComputedProp, isObservableProp, runInAction, toJS } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Character } from "../../src/app/charactersApi";
import { CharactersState } from "../../src/app/charactersState";
import {
  CharacterScreenState,
  commitName,
  commitPersona,
  flushCharacterEdits,
  isDirty,
  isDraft,
  isNewCharacter,
  loadCharacter,
  submitArchive,
  submitCreate,
  submitRestore,
} from "../../src/app/characterScreenState";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- the spec's four sentences
const CREATE_ERROR = "Could not create the character.";
const SAVE_ERROR = "Could not save the character.";
const ARCHIVE_ERROR = "Could not archive the character.";
const RESTORE_ERROR = "Could not restore the character.";
/** 018's name-field sentence (context.md UI strings). */
const NAME_ERROR = "A character needs a name.";

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
describe("the new-mode state", () => {
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

  it("the class carries no method and no computed getter (009 DoD-1, field list widened by 018 008) — DoD-11", () => {
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
      "nameError",
      "nameSaving",
      "personaSaving",
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

  it("the derivations and the effects are free functions, not members (009 DoD-1, re-listed by 018 008) — DoD-11", () => {
    for (const fn of [
      isNewCharacter,
      isDirty,
      isDraft,
      loadCharacter,
      submitCreate,
      commitName,
      commitPersona,
      flushCharacterEdits,
      submitArchive,
      submitRestore,
    ]) {
      expect(typeof fn).toBe("function");
    }
    const members = Object.getOwnPropertyNames(CharacterScreenState.prototype);
    for (const name of ["commitName", "commitPersona", "flushCharacterEdits", "isDraft"]) {
      expect(members).not.toContain(name);
    }
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
describe("isDirty around a loaded character", () => {
  async function loadedViaServer(): Promise<CharacterScreenState> {
    stubBackend(() => jsonResponse(LOADED, 200));
    const state = new CharacterScreenState(ID);
    await loadCharacter(state);
    return state;
  }

  it("right after a successful load isDirty does not hold (009 DoD-5, canSubmit dropped) — DoD-11", async () => {
    const state = await loadedViaServer();
    expect(isDirty(state)).toBe(false);
  });

  it("changing the draft name makes isDirty true (009 DoD-5, canSubmit dropped) — DoD-11", async () => {
    const state = await loadedViaServer();
    runInAction(() => {
      state.name = "Aria Vancet";
    });
    expect(isDirty(state)).toBe(true);
  });

  it("changing the draft sheet makes isDirty true (009 DoD-5, canSubmit dropped) — DoD-11", async () => {
    const state = await loadedViaServer();
    runInAction(() => {
      state.sheet = `${LOADED.sheet}\n\nAnd a second paragraph.`;
    });
    expect(isDirty(state)).toBe(true);
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

  it("an archive after a save failure clears the save sentence before its request (009 DoD-11, the save is now the name commit) — DoD-11", async () => {
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

    await commitName(state, characters);
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

// ===========================================================================
// Feature 018, step 008 — the draft page and blur-save.
// ===========================================================================

// ---------------------------------------------------------------- 018 fixtures
// Timestamps are fixed-width text; "not older" is their order (008.context.md).
const T_LOADED = "2026-05-01T10:00:00.000000+00:00";
const T_RENAMED = "2026-05-01T10:05:00.000000+00:00";
const T_PERSONA = "2026-05-01T10:06:00.000000+00:00";
const T_ARCHIVED = "2026-05-01T10:07:00.000000+00:00";
const T_LATER = "2026-05-01T10:08:00.000000+00:00";

/** The loaded character "Aria" of DoD-5..DoD-10. */
const ARIA: Character = {
  id: ID,
  name: "Aria",
  sheet: "# Aria",
  archived_at: null,
  created_at: T_LOADED,
  updated_at: T_LOADED,
};

const ARIA_RENAMED: Character = { ...ARIA, name: "Aria Vale", updated_at: T_RENAMED };

const NEW_SHEET = "# Aria\n\nA cartographer of drowned cities.";
const ARIA_PERSONA: Character = { ...ARIA, sheet: NEW_SHEET, updated_at: T_PERSONA };

const ARIA_ARCHIVED: Character = { ...ARIA, archived_at: T_ARCHIVED, updated_at: T_ARCHIVED };

/** What the create of the draft "Aria" / "# Aria" answers. */
const ARIA_CREATED: Character = {
  id: NEW_ID,
  name: "Aria",
  sheet: "# Aria",
  archived_at: null,
  created_at: T_LOADED,
  updated_at: T_LOADED,
};

function isPatch(request: Seen): boolean {
  return request.method === "PATCH" && request.path === ITEM_PATH;
}

function isCreate(request: Seen): boolean {
  return request.method === "POST" && request.path === COLLECTION_PATH && request.search === "";
}

function patchBody(request: Seen): Record<string, unknown> {
  return request.body as Record<string, unknown>;
}

// ---------------------------------------------------------------------------
describe("018 step 008 — the draft and submitCreate's guard", () => {
  it("a state constructed with null is a draft, ready, with no character — DoD-1", () => {
    const state = new CharacterScreenState(null);
    expect(isDraft(state)).toBe(true);
    expect(state.status).toBe("ready");
    expect(state.character).toBeNull();
    expect(state.nameError).toBeNull();
    expect(state.nameSaving).toBe(false);
    expect(state.personaSaving).toBe(false);
  });

  it("a state constructed with an id is not a draft — DoD-1", () => {
    expect(isDraft(new CharacterScreenState(ID))).toBe(false);
  });

  it.each(["", "   ", "\t", "\n  \n"])(
    "submitCreate with a blank name (case %#) sends no request and does not call onCreated — DoD-1",
    async (name) => {
      const { calls } = stubBackend(() => jsonResponse(ARIA_CREATED, 201));
      const state = newScreen(name, "");
      const onCreated = vi.fn<(characterId: string) => void>();
      await expect(submitCreate(state, workspaceWith([]), onCreated)).resolves.toBeUndefined();
      await flush();
      expect(calls).toHaveLength(0);
      expect(onCreated).not.toHaveBeenCalled();
      expect(isDraft(state)).toBe(true);
    },
  );

  it("submitCreate with a persona typed and the name blank still sends nothing — DoD-1", async () => {
    const { calls } = stubBackend(() => jsonResponse(ARIA_CREATED, 201));
    const state = newScreen("   ", "# Aria\n\nA persona with no name yet.");
    const characters = workspaceWith([OTHER]);
    const onCreated = vi.fn<(characterId: string) => void>();
    await submitCreate(state, characters, onCreated);
    await flush();
    expect(calls).toHaveLength(0);
    expect(onCreated).not.toHaveBeenCalled();
    expect(isDraft(state)).toBe(true);
    expect(rows(characters)).toEqual([OTHER]);
  });
});

// ---------------------------------------------------------------------------
describe("018 step 008 — creating the character from the draft", () => {
  it("posts exactly the draft's name and sheet to /api/characters — DoD-2", async () => {
    const { calls } = stubBackend(() => jsonResponse(ARIA_CREATED, 201));
    await submitCreate(newScreen("Aria", "# Aria"), workspaceWith([]), () => {});
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].path).toBe(COLLECTION_PATH);
    expect(calls[0].body).toEqual({ name: "Aria", sheet: "# Aria" });
  });

  it("on the 201 calls onCreated once with the id string, lists the row, and ends the draft — DoD-2", async () => {
    stubBackend(() => jsonResponse(ARIA_CREATED, 201));
    const state = newScreen("Aria", "# Aria");
    const characters = workspaceWith([OTHER]);
    const onCreated = vi.fn<(characterId: string) => void>();

    await expect(submitCreate(state, characters, onCreated)).resolves.toBeUndefined();

    expect(onCreated).toHaveBeenCalledTimes(1);
    expect(onCreated).toHaveBeenCalledWith(NEW_ID);
    expect(typeof onCreated.mock.calls[0][0]).toBe("string");
    expect(rows(characters).find((row) => row.id === NEW_ID)).toEqual(ARIA_CREATED);
    expect(isDraft(state)).toBe(false);
    expect(toJS(state.character)).toEqual(ARIA_CREATED);
    expect(state.name).toBe("Aria");
    expect(state.sheet).toBe("# Aria");
    expect(state.submitStatus).toBe("idle");
  });

  it("a second submitCreate while the first is pending sends no second request — DoD-3", async () => {
    const pending = deferred<Response>();
    const { calls } = stubBackend(() => pending.promise);
    const state = newScreen("Aria", "# Aria");
    const characters = workspaceWith([]);
    const onCreated = vi.fn<(characterId: string) => void>();

    const first = submitCreate(state, characters, onCreated);
    await flush();
    const second = submitCreate(state, characters, onCreated);
    await flush();
    expect(calls).toHaveLength(1);

    pending.resolve(jsonResponse(ARIA_CREATED, 201));
    await expect(first).resolves.toBeUndefined();
    await expect(second).resolves.toBeUndefined();
    expect(calls).toHaveLength(1);
    expect(onCreated).toHaveBeenCalledTimes(1);
  });

  it("a submitCreate after a successful create sends nothing — DoD-3", async () => {
    const { calls } = stubBackend(() => jsonResponse(ARIA_CREATED, 201));
    const state = newScreen("Aria", "# Aria");
    const characters = workspaceWith([]);
    const onCreated = vi.fn<(characterId: string) => void>();

    await submitCreate(state, characters, onCreated);
    expect(calls).toHaveLength(1);

    await submitCreate(state, characters, onCreated);
    runInAction(() => {
      state.name = "Aria Again";
    });
    await submitCreate(state, characters, onCreated);
    await flush();

    expect(calls).toHaveLength(1);
    expect(onCreated).toHaveBeenCalledTimes(1);
    expect(ids(characters)).toEqual([NEW_ID]);
  });

  it.each(FAILURES)(
    "a failed create (%s) keeps the draft, calls nothing and leaves the workspace alone — DoD-4",
    async (_label, answer) => {
      stubBackend(() => answer());
      const state = newScreen("Aria", "# Aria");
      const characters = workspaceWith([OTHER]);
      const onCreated = vi.fn<(characterId: string) => void>();

      await expect(submitCreate(state, characters, onCreated)).resolves.toBeUndefined();

      expect(state.error).toBe(CREATE_ERROR);
      expect(state.name).toBe("Aria");
      expect(state.sheet).toBe("# Aria");
      expect(isDraft(state)).toBe(true);
      expect(state.character).toBeNull();
      expect(onCreated).not.toHaveBeenCalled();
      expect(rows(characters)).toEqual([OTHER]);
      expect(state.submitStatus).toBe("idle");
    },
  );

  it("a transport failure on create behaves the same way — DoD-4", async () => {
    stubBackend(() => {
      throw new TypeError("Failed to fetch");
    });
    const state = newScreen("Aria", "# Aria");
    const characters = workspaceWith([OTHER]);
    const onCreated = vi.fn<(characterId: string) => void>();

    await expect(submitCreate(state, characters, onCreated)).resolves.toBeUndefined();

    expect(state.error).toBe(CREATE_ERROR);
    expect(state.name).toBe("Aria");
    expect(state.sheet).toBe("# Aria");
    expect(isDraft(state)).toBe(true);
    expect(onCreated).not.toHaveBeenCalled();
    expect(rows(characters)).toEqual([OTHER]);
  });
});

// ---------------------------------------------------------------------------
describe("018 step 008 — the name commit", () => {
  it("an unchanged name sends nothing — DoD-5", async () => {
    const { calls } = stubBackend(() => jsonResponse(ARIA_RENAMED, 200));
    const state = loadedScreen(ARIA);
    await expect(commitName(state, workspaceWith([ARIA]))).resolves.toBeUndefined();
    await flush();
    expect(calls).toHaveLength(0);
    expect(toJS(state.character)).toEqual(ARIA);
  });

  it("a changed name PATCHes exactly {name}, then character and the workspace hold the served row — DoD-5", async () => {
    const pending = deferred<Response>();
    const { calls } = stubBackend(() => pending.promise);
    const state = loadedScreen(ARIA);
    const characters = workspaceWith([ARIA, OTHER]);
    runInAction(() => {
      state.name = "Aria Vale";
    });

    const running = commitName(state, characters);
    await flush();

    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("PATCH");
    expect(calls[0].path).toBe(ITEM_PATH);
    expect(calls[0].body).toEqual({ name: "Aria Vale" });
    // Never optimistic: the held row stands until the answer.
    expect(toJS(state.character)).toEqual(ARIA);

    pending.resolve(jsonResponse(ARIA_RENAMED, 200));
    await expect(running).resolves.toBeUndefined();

    expect(toJS(state.character)).toEqual(ARIA_RENAMED);
    expect(rows(characters).find((row) => row.id === ID)).toEqual(ARIA_RENAMED);
    expect(state.name).toBe("Aria Vale");
  });

  it("a name sent with spaces adopts the server's trimmed name, and a later commit sends nothing — DoD-5", async () => {
    const { calls } = stubBackend(() => jsonResponse(ARIA_RENAMED, 200));
    const state = loadedScreen(ARIA);
    const characters = workspaceWith([ARIA]);
    runInAction(() => {
      state.name = "  Aria Vale ";
    });

    await commitName(state, characters);
    expect(calls).toHaveLength(1);
    expect(calls[0].body).toEqual({ name: "  Aria Vale " });
    expect(state.name).toBe("Aria Vale");

    await commitName(state, characters);
    await flush();
    expect(calls).toHaveLength(1);
  });

  it("a blank name sends nothing, sets the name error and keeps the typed text — DoD-5", async () => {
    const { calls } = stubBackend(() => jsonResponse(ARIA_RENAMED, 200));
    const state = loadedScreen(ARIA);
    const characters = workspaceWith([ARIA]);
    runInAction(() => {
      state.name = "   ";
    });

    await expect(commitName(state, characters)).resolves.toBeUndefined();
    await flush();

    expect(calls).toHaveLength(0);
    expect(state.nameError).toBe(NAME_ERROR);
    expect(state.name).toBe("   ");
    expect(state.character?.name).toBe("Aria");
    expect(rows(characters)).toEqual([ARIA]);
  });

  it("a later commit with a non-blank changed name clears the name error and saves — DoD-5", async () => {
    const { calls } = stubBackend(() => jsonResponse(ARIA_RENAMED, 200));
    const state = loadedScreen(ARIA);
    const characters = workspaceWith([ARIA]);
    runInAction(() => {
      state.name = "   ";
    });
    await commitName(state, characters);
    expect(state.nameError).toBe(NAME_ERROR);

    runInAction(() => {
      state.name = "Aria Vale";
    });
    await commitName(state, characters);

    expect(state.nameError).toBeNull();
    expect(calls).toHaveLength(1);
    expect(calls[0].body).toEqual({ name: "Aria Vale" });
  });

  it("a later commit with the unchanged non-blank name clears the name error and sends nothing — DoD-5", async () => {
    const { calls } = stubBackend(() => jsonResponse(ARIA_RENAMED, 200));
    const state = loadedScreen(ARIA);
    const characters = workspaceWith([ARIA]);
    runInAction(() => {
      state.name = "";
    });
    await commitName(state, characters);
    expect(state.nameError).toBe(NAME_ERROR);

    runInAction(() => {
      state.name = "Aria";
    });
    await commitName(state, characters);
    await flush();

    expect(state.nameError).toBeNull();
    expect(calls).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
describe("018 step 008 — the persona commit", () => {
  it("an unchanged sheet sends nothing — DoD-6", async () => {
    const { calls } = stubBackend(() => jsonResponse(ARIA_PERSONA, 200));
    const state = loadedScreen(ARIA);
    await expect(commitPersona(state, workspaceWith([ARIA]))).resolves.toBeUndefined();
    await flush();
    expect(calls).toHaveLength(0);
  });

  it("a changed sheet PATCHes exactly {sheet} and leaves an unsaved name edit untouched — DoD-6", async () => {
    const { calls } = stubBackend(() => jsonResponse(ARIA_PERSONA, 200));
    const state = loadedScreen(ARIA);
    const characters = workspaceWith([ARIA, OTHER]);
    runInAction(() => {
      state.name = "Aria the Unsaved";
      state.sheet = NEW_SHEET;
    });

    await expect(commitPersona(state, characters)).resolves.toBeUndefined();

    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("PATCH");
    expect(calls[0].path).toBe(ITEM_PATH);
    expect(calls[0].body).toEqual({ sheet: NEW_SHEET });
    expect(state.name).toBe("Aria the Unsaved");
    expect(state.sheet).toBe(NEW_SHEET);
    expect(toJS(state.character)).toEqual(ARIA_PERSONA);
    expect(rows(characters).find((row) => row.id === ID)).toEqual(ARIA_PERSONA);
  });

  it("text typed during a pending persona save survives the answer and stays dirty — DoD-7", async () => {
    const pending = deferred<Response>();
    const { calls } = stubBackend(() => pending.promise);
    const state = loadedScreen(ARIA);
    const characters = workspaceWith([ARIA]);
    runInAction(() => {
      state.sheet = NEW_SHEET;
    });

    const running = commitPersona(state, characters);
    await flush();
    expect(calls).toHaveLength(1);
    expect(state.personaSaving).toBe(true);

    const newer = `${NEW_SHEET}\n\nAnd a line typed while saving.`;
    runInAction(() => {
      state.sheet = newer;
    });

    pending.resolve(jsonResponse(ARIA_PERSONA, 200));
    await expect(running).resolves.toBeUndefined();

    expect(state.sheet).toBe(newer);
    expect(isDirty(state)).toBe(true);
    expect(state.personaSaving).toBe(false);
  });

  it("a second persona commit during the pending save sends nothing — DoD-7", async () => {
    const pending = deferred<Response>();
    const { calls } = stubBackend(() => pending.promise);
    const state = loadedScreen(ARIA);
    const characters = workspaceWith([ARIA]);
    runInAction(() => {
      state.sheet = NEW_SHEET;
    });

    const first = commitPersona(state, characters);
    await flush();
    runInAction(() => {
      state.sheet = `${NEW_SHEET}\n\nMore.`;
    });
    const second = commitPersona(state, characters);
    await flush();
    expect(calls).toHaveLength(1);

    pending.resolve(jsonResponse(ARIA_PERSONA, 200));
    await expect(first).resolves.toBeUndefined();
    await expect(second).resolves.toBeUndefined();
    expect(calls).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
describe("018 step 008 — an answer older than the held character", () => {
  it("a persona answer older than an archive answered first does not replace character — DoD-8", async () => {
    const patch = deferred<Response>();
    stubBackend((request) => {
      if (isPatch(request)) return patch.promise;
      if (request.method === "POST" && request.path === ARCHIVE_PATH) {
        return jsonResponse(ARIA_ARCHIVED, 200);
      }
      return serverError();
    });
    const state = loadedScreen(ARIA);
    const characters = workspaceWith([ARIA], true);
    runInAction(() => {
      state.sheet = NEW_SHEET;
    });

    const saving = commitPersona(state, characters);
    await flush();
    await submitArchive(state, characters);
    expect(toJS(state.character)).toEqual(ARIA_ARCHIVED);

    // ARIA_PERSONA's updated_at (10:06) is older than the archive's (10:07).
    patch.resolve(jsonResponse(ARIA_PERSONA, 200));
    await expect(saving).resolves.toBeUndefined();

    expect(toJS(state.character)).toEqual(ARIA_ARCHIVED);
  });

  it("a name answer older than the held character does not replace it — DoD-8", async () => {
    stubBackend(() => jsonResponse(ARIA_RENAMED, 200));
    const held: Character = { ...ARIA, updated_at: T_LATER };
    const state = loadedScreen(held);
    runInAction(() => {
      state.name = "Aria Vale";
    });

    await commitName(state, workspaceWith([held]));

    expect(toJS(state.character)).toEqual(held);
  });

  it("a newer answer does replace character — DoD-8", async () => {
    const newer: Character = { ...ARIA_ARCHIVED, sheet: NEW_SHEET, updated_at: T_LATER };
    stubBackend(() => jsonResponse(newer, 200));
    const state = loadedScreen(ARIA_ARCHIVED);
    runInAction(() => {
      state.sheet = NEW_SHEET;
    });

    await commitPersona(state, workspaceWith([ARIA_ARCHIVED], true));

    expect(toJS(state.character)).toEqual(newer);
  });

  it("an answer with the same updated_at is not older and replaces character — DoD-8", async () => {
    const same: Character = { ...ARIA, name: "Aria Vale" };
    stubBackend(() => jsonResponse(same, 200));
    const state = loadedScreen(ARIA);
    runInAction(() => {
      state.name = "Aria Vale";
    });

    await commitName(state, workspaceWith([ARIA]));

    expect(toJS(state.character)).toEqual(same);
  });
});

// ---------------------------------------------------------------------------
describe("018 step 008 — a failed save", () => {
  it.each(FAILURES)(
    "a failed name save (%s) sets the save sentence, keeps the typed name and the character — DoD-9",
    async (_label, answer) => {
      stubBackend(() => answer());
      const state = loadedScreen(ARIA);
      const characters = workspaceWith([ARIA]);
      runInAction(() => {
        state.name = "Aria Vale";
      });

      await expect(commitName(state, characters)).resolves.toBeUndefined();

      expect(state.error).toBe(SAVE_ERROR);
      expect(state.name).toBe("Aria Vale");
      expect(toJS(state.character)).toEqual(ARIA);
      expect(rows(characters)).toEqual([ARIA]);
    },
  );

  it.each(FAILURES)(
    "a failed persona save (%s) sets the save sentence, keeps the typed sheet and the character — DoD-9",
    async (_label, answer) => {
      stubBackend(() => answer());
      const state = loadedScreen(ARIA);
      const characters = workspaceWith([ARIA]);
      runInAction(() => {
        state.sheet = NEW_SHEET;
      });

      await expect(commitPersona(state, characters)).resolves.toBeUndefined();

      expect(state.error).toBe(SAVE_ERROR);
      expect(state.sheet).toBe(NEW_SHEET);
      expect(toJS(state.character)).toEqual(ARIA);
      expect(rows(characters)).toEqual([ARIA]);
    },
  );

  it("a transport failure on either save behaves the same way — DoD-9", async () => {
    stubBackend(() => {
      throw new TypeError("Failed to fetch");
    });

    const naming = loadedScreen(ARIA);
    runInAction(() => {
      naming.name = "Aria Vale";
    });
    await expect(commitName(naming, workspaceWith([ARIA]))).resolves.toBeUndefined();
    expect(naming.error).toBe(SAVE_ERROR);
    expect(naming.name).toBe("Aria Vale");
    expect(toJS(naming.character)).toEqual(ARIA);

    const writing = loadedScreen(ARIA);
    runInAction(() => {
      writing.sheet = NEW_SHEET;
    });
    await expect(commitPersona(writing, workspaceWith([ARIA]))).resolves.toBeUndefined();
    expect(writing.error).toBe(SAVE_ERROR);
    expect(writing.sheet).toBe(NEW_SHEET);
    expect(toJS(writing.character)).toEqual(ARIA);
  });
});

// ---------------------------------------------------------------------------
describe("018 step 008 — the flush", () => {
  /** Answers a name PATCH and a sheet PATCH each with its own row; a create with ARIA_CREATED. */
  function flushBackend() {
    return stubBackend((request) => {
      if (isPatch(request)) {
        const body = patchBody(request);
        if ("name" in body) return jsonResponse(ARIA_RENAMED, 200);
        if ("sheet" in body) return jsonResponse(ARIA_PERSONA, 200);
      }
      if (isCreate(request)) return jsonResponse(ARIA_CREATED, 201);
      return serverError();
    });
  }

  it("on a loaded character with a changed name and sheet sends one name PATCH and one sheet PATCH — DoD-10", async () => {
    const { calls } = flushBackend();
    const state = loadedScreen(ARIA);
    runInAction(() => {
      state.name = "Aria Vale";
      state.sheet = NEW_SHEET;
    });

    await expect(flushCharacterEdits(state, workspaceWith([ARIA]))).resolves.toBeUndefined();
    await flush();

    expect(calls).toHaveLength(2);
    expect(calls.every(isPatch)).toBe(true);
    const bodies = calls.map((call) => call.body);
    expect(bodies).toEqual(
      expect.arrayContaining([{ name: "Aria Vale" }, { sheet: NEW_SHEET }]),
    );
  });

  it("on a draft with name Aria posts the create once — DoD-10", async () => {
    const { calls } = flushBackend();
    const state = newScreen("Aria", "# Aria");
    const characters = workspaceWith([]);

    await expect(flushCharacterEdits(state, characters)).resolves.toBeUndefined();
    await flush();

    expect(calls).toHaveLength(1);
    expect(isCreate(calls[0])).toBe(true);
    expect(calls[0].body).toEqual({ name: "Aria", sheet: "# Aria" });
    expect(rows(characters).find((row) => row.id === NEW_ID)).toEqual(ARIA_CREATED);
  });

  it("on a loaded character with nothing changed sends nothing — DoD-10", async () => {
    const { calls } = flushBackend();
    await expect(
      flushCharacterEdits(loadedScreen(ARIA), workspaceWith([ARIA])),
    ).resolves.toBeUndefined();
    await flush();
    expect(calls).toHaveLength(0);
  });

  it.each([
    ["an empty draft", "", ""],
    ["a draft with only a persona", "   ", "# A persona with no name"],
  ])("on %s sends nothing — DoD-10", async (_label, name, sheet) => {
    const { calls } = flushBackend();
    await expect(
      flushCharacterEdits(newScreen(name, sheet), workspaceWith([])),
    ).resolves.toBeUndefined();
    await flush();
    expect(calls).toHaveLength(0);
  });

  it("on a loaded character with a blank name and a changed sheet sends only the sheet PATCH — DoD-10", async () => {
    const { calls } = flushBackend();
    const state = loadedScreen(ARIA);
    runInAction(() => {
      state.name = "  ";
      state.sheet = NEW_SHEET;
    });

    await flushCharacterEdits(state, workspaceWith([ARIA]));
    await flush();

    expect(calls).toHaveLength(1);
    expect(isPatch(calls[0])).toBe(true);
    expect(calls[0].body).toEqual({ sheet: NEW_SHEET });
  });
});
