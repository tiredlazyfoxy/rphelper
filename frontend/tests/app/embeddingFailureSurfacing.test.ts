// Feature 024, step 008 — the four authoring effects surface the embedding sentences
// (DoD-2..DoD-5). DoD-1 lives in `tests/shared/embeddingFailure.test.ts`; DoD-6 is
// [manual/live] and carries no test.
//
// Expected values come from the spec and the `## Skeleton` record alone — no source file of
// the three state modules was read:
//   - the two sentences are imported from `src/shared/embeddingFailure` (the exported
//     constants `008.context.md` says to compare against, pinned verbatim in DoD-1);
//   - the generic fallback sentences are literals from the `## Skeleton` channel table
//     ("Could not save the note." / "Could not save the character." / "Could not create the
//     setup." / "Could not save the setup.", the last two chosen by `draft.original === null`);
//   - each effect's channel is read exactly as that table records it: `noteFailure(state,
//     memoId)`, `state.newNote?.failure`, `state.error`, `draft.error`;
//   - the routes are the `## Skeleton` / harvest B8 stub table;
//   - `context.md`'s Wire contract gives the two codes and their statuses (409 / 502), and
//     the third case of each group is the pre-existing generic sentence, unchanged — the
//     regression half that proves the change is additive.
//
// The character surface is `commitPersona`, not the step file's `submitSave`: see
// `## Ultra phase` (3) and the `## Skeleton` binding correction. D5 embeds only a **changed
// `sheet`**, so `commitPersona` is the only character save that can receive these codes.
//
// Conventions (`context.md` "Test conventions"): Vitest/jsdom with `globals: false`, so every
// symbol is imported explicitly; `fetch` is stubbed per test with `vi.stubGlobal`, keyed on
// method + pathname; every id is a decimal string past Number.MAX_SAFE_INTEGER. None of the
// four effects notifies (`## Skeleton`), so no notification mock is registered here.
import { runInAction } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Character } from "../../src/app/charactersApi";
import { CharactersState } from "../../src/app/charactersState";
import { CharacterScreenState, commitPersona } from "../../src/app/characterScreenState";
import type { Memo } from "../../src/app/memosApi";
import {
  MemoLevelState,
  noteFailure,
  openNewNote,
  populateMemoLevel,
  saveNewNote,
  saveNote,
  setNewNoteText,
  setNoteText,
} from "../../src/app/memoLevelState";
import {
  setDraftDescription,
  setDraftName,
  SetupDraft,
  submitSetup,
} from "../../src/app/setupDraft";
import type { Setup } from "../../src/app/setupsApi";
import { LLM_UNREACHABLE_SENTENCE, NO_EMBEDDING_MODEL_SENTENCE } from "../../src/shared/embeddingFailure";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string };

// ---------------------------------------------------------------- the generic sentences
// From the `## Skeleton` channel table — today's behaviour, which the third case of each
// group must keep byte for byte.
const NOTE_SAVE_FAILED = "Could not save the note.";
const CHARACTER_SAVE_FAILED = "Could not save the character.";
const SETUP_CREATE_FAILED = "Could not create the setup.";
const SETUP_SAVE_FAILED = "Could not save the setup.";

// ---------------------------------------------------------------- the third case's code
// A generic refusal: not one of the two embedding codes, so the helper answers null and the
// fallback stands (harvest C10 — this is what every existing failure test already stubs).
const OTHER_CODE = "internal_error";
const OTHER_STATUS = 500;

// ---------------------------------------------------------------- fixtures
const CHARACTER_ID = "7250000000000000001";
const MEMO_ID = "7250000000000000201";
const SETUP_ID = "7260000000000000001";

const STAMP = "2026-10-04T09:26:53.000000+00:00";

const MEMO_PATH = `/api/memos/${MEMO_ID}`;
const MEMO_COLLECTION_PATH = "/api/memos";
const CHARACTER_PATH = `/api/characters/${CHARACTER_ID}`;
const SETUP_COLLECTION_PATH = `/api/characters/${CHARACTER_ID}/setups`;
const SETUP_ITEM_PATH = `/api/setups/${SETUP_ID}`;

const MEMO_ROW: Memo = {
  id: MEMO_ID,
  scope: "character",
  scope_id: CHARACTER_ID,
  body: "Old body",
  is_enabled: true,
  is_forced: false,
  sort_key: 0,
  created_at: STAMP,
  updated_at: STAMP,
};

const ARIA: Character = {
  id: CHARACTER_ID,
  name: "Aria",
  sheet: "# Aria",
  archived_at: null,
  created_at: STAMP,
  updated_at: STAMP,
};

const NEW_SHEET = "# Aria\n\nA cartographer of drowned cities.";

const TAVERN: Setup = {
  id: SETUP_ID,
  character_id: CHARACTER_ID,
  name: "The Gilded Tavern",
  description: "# The Gilded Tavern\n\nSmoke and lute strings.",
  archived_at: null,
  created_at: STAMP,
  updated_at: STAMP,
};

const TYPED_SETUP_NAME = "Nightfall Harbour ";
const TYPED_SETUP_DESCRIPTION = "# Nightfall Harbour\n\nTwo ships, no harbourmaster.";

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

/** The domain envelope every non-2xx of ours carries (`context.md` Wire contract). */
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

/**
 * Refuses `METHOD pathname` with `envelope(code, status)`; anything else gets a 404 whose
 * code is neither embedding code, so a request to the wrong route cannot pass a test.
 */
function refuseRoute(route: string, code: string, status: number): Seen[] {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    calls.push({ method, path: url.pathname });
    if (`${method} ${url.pathname}` === route) return envelope(code, status);
    return envelope("route_not_stubbed", 404);
  });
  vi.stubGlobal("fetch", mock);
  return calls;
}

function expectOneRequest(calls: Seen[], method: string, path: string): void {
  expect(calls).toEqual([{ method, path }]);
}

// ---------------------------------------------------------------- effect drivers
/** Edits a held note's text and saves it against a refusing PATCH. */
async function saveNoteRefusedWith(code: string, status: number): Promise<{ surfaced: string | null; calls: Seen[] }> {
  const calls = refuseRoute(`PATCH ${MEMO_PATH}`, code, status);
  const state = new MemoLevelState("character", CHARACTER_ID);
  populateMemoLevel(state, [MEMO_ROW]);
  setNoteText(state, MEMO_ID, "New body");
  await expect(saveNote(state, MEMO_ID)).resolves.toBeUndefined();
  return { surfaced: noteFailure(state, MEMO_ID), calls };
}

/** Opens a new note, types into it and saves it against a refusing POST. */
async function saveNewNoteRefusedWith(
  code: string,
  status: number,
): Promise<{ surfaced: string | null; calls: Seen[] }> {
  const calls = refuseRoute(`POST ${MEMO_COLLECTION_PATH}`, code, status);
  const state = new MemoLevelState("character", CHARACTER_ID);
  populateMemoLevel(state, []);
  openNewNote(state);
  setNewNoteText(state, "A new note");
  await expect(saveNewNote(state)).resolves.toBeUndefined();
  return { surfaced: state.newNote?.failure ?? null, calls };
}

/** A loaded character screen with a changed sheet, committed against a refusing PATCH. */
async function commitPersonaRefusedWith(
  code: string,
  status: number,
): Promise<{ surfaced: string | null; calls: Seen[] }> {
  const calls = refuseRoute(`PATCH ${CHARACTER_PATH}`, code, status);
  const state = new CharacterScreenState(CHARACTER_ID);
  runInAction(() => {
    state.status = "ready";
    state.character = { ...ARIA };
    state.name = ARIA.name;
    state.sheet = NEW_SHEET;
  });
  const characters = new CharactersState();
  runInAction(() => {
    characters.characters = [{ ...ARIA }];
    characters.status = "ready";
  });
  await expect(commitPersona(state, characters)).resolves.toBeUndefined();
  return { surfaced: state.error, calls };
}

/** A create-mode draft submitted against a refusing POST to the character's setups. */
async function submitSetupCreateRefusedWith(
  code: string,
  status: number,
): Promise<{ surfaced: string | null; calls: Seen[]; saved: Setup[] }> {
  const calls = refuseRoute(`POST ${SETUP_COLLECTION_PATH}`, code, status);
  const draft = new SetupDraft(CHARACTER_ID, null);
  setDraftName(draft, TYPED_SETUP_NAME);
  setDraftDescription(draft, TYPED_SETUP_DESCRIPTION);
  const saved: Setup[] = [];
  await expect(
    submitSetup(draft, (row) => {
      saved.push(row);
    }),
  ).resolves.toBeUndefined();
  return { surfaced: draft.error, calls, saved };
}

/** An edit-mode draft with both fields changed, submitted against a refusing PATCH. */
async function submitSetupSaveRefusedWith(
  code: string,
  status: number,
): Promise<{ surfaced: string | null; calls: Seen[]; saved: Setup[] }> {
  const calls = refuseRoute(`PATCH ${SETUP_ITEM_PATH}`, code, status);
  const draft = new SetupDraft(CHARACTER_ID, TAVERN);
  setDraftName(draft, TYPED_SETUP_NAME);
  setDraftDescription(draft, TYPED_SETUP_DESCRIPTION);
  const saved: Setup[] = [];
  await expect(
    submitSetup(draft, (row) => {
      saved.push(row);
    }),
  ).resolves.toBeUndefined();
  return { surfaced: draft.error, calls, saved };
}

// ---------------------------------------------------------------------------
describe("saveNote — a refused memo body edit", () => {
  it("a 409 no_embedding_model surfaces the no_embedding_model sentence through noteFailure — DoD-2", async () => {
    const { surfaced, calls } = await saveNoteRefusedWith("no_embedding_model", 409);
    expect(surfaced).toBe(NO_EMBEDDING_MODEL_SENTENCE);
    expectOneRequest(calls, "PATCH", MEMO_PATH);
  });

  it("a 502 llm_unreachable surfaces the llm_unreachable sentence through noteFailure — DoD-2", async () => {
    const { surfaced, calls } = await saveNoteRefusedWith("llm_unreachable", 502);
    expect(surfaced).toBe(LLM_UNREACHABLE_SENTENCE);
    expectOneRequest(calls, "PATCH", MEMO_PATH);
  });

  it("a 500 with another code still surfaces the generic note-save sentence, unchanged — DoD-2", async () => {
    const { surfaced, calls } = await saveNoteRefusedWith(OTHER_CODE, OTHER_STATUS);
    expect(surfaced).toBe(NOTE_SAVE_FAILED);
    expectOneRequest(calls, "PATCH", MEMO_PATH);
  });
});

// ---------------------------------------------------------------------------
describe("saveNewNote — a refused memo create", () => {
  it("a 409 no_embedding_model surfaces the no_embedding_model sentence on the new note — DoD-3", async () => {
    const { surfaced, calls } = await saveNewNoteRefusedWith("no_embedding_model", 409);
    expect(surfaced).toBe(NO_EMBEDDING_MODEL_SENTENCE);
    expectOneRequest(calls, "POST", MEMO_COLLECTION_PATH);
  });

  it("a 502 llm_unreachable surfaces the llm_unreachable sentence on the new note — DoD-3", async () => {
    const { surfaced, calls } = await saveNewNoteRefusedWith("llm_unreachable", 502);
    expect(surfaced).toBe(LLM_UNREACHABLE_SENTENCE);
    expectOneRequest(calls, "POST", MEMO_COLLECTION_PATH);
  });

  it("a 500 with another code still surfaces the generic note-save sentence, unchanged — DoD-3", async () => {
    const { surfaced, calls } = await saveNewNoteRefusedWith(OTHER_CODE, OTHER_STATUS);
    expect(surfaced).toBe(NOTE_SAVE_FAILED);
    expectOneRequest(calls, "POST", MEMO_COLLECTION_PATH);
  });
});

// ---------------------------------------------------------------------------
describe("commitPersona — a refused persona save", () => {
  it("a 409 no_embedding_model surfaces the no_embedding_model sentence in state.error — DoD-4", async () => {
    const { surfaced, calls } = await commitPersonaRefusedWith("no_embedding_model", 409);
    expect(surfaced).toBe(NO_EMBEDDING_MODEL_SENTENCE);
    expectOneRequest(calls, "PATCH", CHARACTER_PATH);
  });

  it("a 502 llm_unreachable surfaces the llm_unreachable sentence in state.error — DoD-4", async () => {
    const { surfaced, calls } = await commitPersonaRefusedWith("llm_unreachable", 502);
    expect(surfaced).toBe(LLM_UNREACHABLE_SENTENCE);
    expectOneRequest(calls, "PATCH", CHARACTER_PATH);
  });

  it("a 500 with another code still surfaces the generic character-save sentence, unchanged — DoD-4", async () => {
    const { surfaced, calls } = await commitPersonaRefusedWith(OTHER_CODE, OTHER_STATUS);
    expect(surfaced).toBe(CHARACTER_SAVE_FAILED);
    expectOneRequest(calls, "PATCH", CHARACTER_PATH);
  });
});

// ---------------------------------------------------------------------------
describe("submitSetup — a refused setup create", () => {
  it("a 409 no_embedding_model surfaces the no_embedding_model sentence in draft.error — DoD-5", async () => {
    const { surfaced, calls, saved } = await submitSetupCreateRefusedWith("no_embedding_model", 409);
    expect(surfaced).toBe(NO_EMBEDDING_MODEL_SENTENCE);
    expectOneRequest(calls, "POST", SETUP_COLLECTION_PATH);
    expect(saved).toEqual([]);
  });

  it("a 502 llm_unreachable surfaces the llm_unreachable sentence in draft.error — DoD-5", async () => {
    const { surfaced, calls, saved } = await submitSetupCreateRefusedWith("llm_unreachable", 502);
    expect(surfaced).toBe(LLM_UNREACHABLE_SENTENCE);
    expectOneRequest(calls, "POST", SETUP_COLLECTION_PATH);
    expect(saved).toEqual([]);
  });

  it("a 500 with another code still surfaces the generic setup-create sentence, unchanged — DoD-5", async () => {
    const { surfaced, calls, saved } = await submitSetupCreateRefusedWith(OTHER_CODE, OTHER_STATUS);
    expect(surfaced).toBe(SETUP_CREATE_FAILED);
    expectOneRequest(calls, "POST", SETUP_COLLECTION_PATH);
    expect(saved).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("submitSetup — a refused setup save", () => {
  it("a 409 no_embedding_model surfaces the no_embedding_model sentence in draft.error — DoD-5", async () => {
    const { surfaced, calls, saved } = await submitSetupSaveRefusedWith("no_embedding_model", 409);
    expect(surfaced).toBe(NO_EMBEDDING_MODEL_SENTENCE);
    expectOneRequest(calls, "PATCH", SETUP_ITEM_PATH);
    expect(saved).toEqual([]);
  });

  it("a 502 llm_unreachable surfaces the llm_unreachable sentence in draft.error — DoD-5", async () => {
    const { surfaced, calls, saved } = await submitSetupSaveRefusedWith("llm_unreachable", 502);
    expect(surfaced).toBe(LLM_UNREACHABLE_SENTENCE);
    expectOneRequest(calls, "PATCH", SETUP_ITEM_PATH);
    expect(saved).toEqual([]);
  });

  it("a 500 with another code still surfaces the generic setup-save sentence, unchanged — DoD-5", async () => {
    const { surfaced, calls, saved } = await submitSetupSaveRefusedWith(OTHER_CODE, OTHER_STATUS);
    expect(surfaced).toBe(SETUP_SAVE_FAILED);
    expectOneRequest(calls, "PATCH", SETUP_ITEM_PATH);
    expect(saved).toEqual([]);
  });
});
