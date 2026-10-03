// Feature 018, step 006 — the character configuration block's state (DoD-4..DoD-9).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 006.context.md ("017's character routes, as declared", "Why the lines are derived
// client-side") and context.md: D9, the UI strings table (Model control, resolved-value
// lines, Configuration save failure) and "Test conventions". Every expected sentence and
// label is a literal from the strings table, never computed by calling a derivation.
// Requests are stubbed and recorded by exact method + pathname + query.
import { runInAction, toJS } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CharacterConfiguration, EnabledModel, ModelRef } from "../../src/app/configurationApi";
import {
  CharacterConfigState,
  UNSET_MODEL_VALUE,
  commitPromptDraft,
  loadCharacterConfig,
  modelChoices,
  modelLine,
  promptLine,
  saveCharacterConfig,
  selectedModelValue,
  setPromptDraft,
  toolChoice,
  toolLine,
  toolPatchValue,
  type ModelChoice,
} from "../../src/app/characterConfigState";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };
type Handler = (request: Seen, init?: RequestInit) => Response | Promise<Response>;

// ---------------------------------------------------------------- the spec's names
const CHARACTER_ID = "7250000000000000001";
const CONFIG_PATH = "/api/characters/7250000000000000001/configuration";
const MODELS_PATH = "/api/models";

const FIRST_ENABLED_MODEL = "First enabled model";
const MODEL_NOT_SET = "Not set: new sessions take the first enabled model.";
const SET_HERE = "Set on this character.";
const PROMPT_NOT_SET = "Not set: no system prompt.";
const TOOL_DEFAULT = "On (default)";
const TOOL_ON_HERE = "On (set on this character)";
const TOOL_OFF_HERE = "Off (set on this character)";
const NO_LONGER_ENABLED = "That model is no longer enabled.";
const COULD_NOT_SAVE = "Could not save the configuration.";

// ---------------------------------------------------------------- payload builders
const SERVER_1 = "7250000000000000301";
const SERVER_2 = "7250000000000000302";

function enabled(server_id: string, server_name: string, model_name: string): EnabledModel {
  return { server_id, server_name, model_name };
}

// Model A on server S1, model B on server S2 (DoD-4's "A (S1)", "B (S2)").
const MODEL_A = enabled(SERVER_1, "Box One", "alpha-13b");
const MODEL_B = enabled(SERVER_2, "Box Two", "zeta-7b");
const LABEL_A = "alpha-13b (Box One)";
const LABEL_B = "zeta-7b (Box Two)";
const LABEL_A_NOT_ENABLED = "alpha-13b (not enabled)";

function ref(model: EnabledModel): ModelRef {
  return { server_id: model.server_id, model_name: model.model_name };
}

/** A wire CharacterConfiguration with all five keys. */
function configuration(overrides: Partial<CharacterConfiguration> = {}): CharacterConfiguration {
  return {
    model: null,
    system_prompt: null,
    tool_memo_search: null,
    tool_session_search: null,
    tool_web_search: null,
    ...overrides,
  };
}

/** DoD-4's configuration: model A on S1, prompt null, memo null, session false, web true. */
function dod4Configuration(): CharacterConfiguration {
  return configuration({
    model: ref(MODEL_A),
    system_prompt: null,
    tool_memo_search: null,
    tool_session_search: false,
    tool_web_search: true,
  });
}

// ---------------------------------------------------------------- harness
beforeEach(() => {
  notifyFailureSpy.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function rawBody(init?: RequestInit): string | undefined {
  const raw = init?.body;
  if (raw === undefined || raw === null) return undefined;
  return String(raw);
}

function parseBody(init?: RequestInit): unknown {
  const raw = rawBody(init);
  return raw === undefined ? undefined : (JSON.parse(raw) as unknown);
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number, detail: unknown = {}): Response {
  return jsonResponse({ error: { code, message: "kv-19 backend prose.", detail } }, status);
}

function notEnabledEnvelope(model: ModelRef): Response {
  return envelope("model_not_enabled", 409, {
    server_id: model.server_id,
    model_name: model.model_name,
    level: "character",
  });
}

type Routes = Record<string, Handler>;

/** Answers by exact `METHOD path?query`; anything else is a 500 and is still recorded. */
function stubRoutes(routes: Routes) {
  const calls: Seen[] = [];
  const raws: (string | undefined)[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      search: url.search,
      body: parseBody(init),
    };
    calls.push(request);
    raws.push(rawBody(init));
    const answer = routes[`${request.method} ${request.path}${request.search}`];
    if (answer === undefined) return envelope("unexpected_request", 500);
    return answer(request, init);
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls, raws };
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

function snapshot(state: CharacterConfigState) {
  return {
    characterId: state.characterId,
    configuration: toJS(state.configuration),
    configStatus: state.configStatus,
    models: toJS(state.models),
    modelsStatus: state.modelsStatus,
    promptDraft: state.promptDraft,
    savingKey: state.savingKey,
    failure: state.failure,
  };
}

/** A state as a successful load leaves it: both ready, draft seeded from the prompt. */
function readyState(config: CharacterConfiguration, models: EnabledModel[]): CharacterConfigState {
  const state = new CharacterConfigState(CHARACTER_ID);
  runInAction(() => {
    state.configuration = configuration({ ...config, model: config.model === null ? null : { ...config.model } });
    state.models = models.map((model) => ({ ...model }));
    state.configStatus = "ready";
    state.modelsStatus = "ready";
    state.promptDraft = config.system_prompt ?? "";
  });
  return state;
}

function loadRoutes(config: CharacterConfiguration, models: EnabledModel[]): Routes {
  return {
    [`GET ${CONFIG_PATH}`]: () => jsonResponse(config, 200),
    [`GET ${MODELS_PATH}`]: () => jsonResponse({ models }, 200),
  };
}

function count(calls: Seen[], method: string, path: string): number {
  return calls.filter((call) => call.method === method && call.path === path).length;
}

function selected(state: CharacterConfigState): ModelChoice | undefined {
  const value = selectedModelValue(state);
  return modelChoices(state).find((choice) => choice.value === value);
}

const FAILURE_ANSWERS: [label: string, answer: () => Response][] = [
  ["a 500 envelope", () => envelope("internal_error", 500)],
  ["a 404 envelope", () => envelope("character_not_found", 404)],
  [
    "a transport failure",
    () => {
      throw new TypeError("Failed to fetch");
    },
  ],
];

// ===========================================================================
describe("loadCharacterConfig over DoD-4's configuration and models [A, B]", () => {
  it("requests exactly GET /api/characters/<id>/configuration and GET /api/models — DoD-4", async () => {
    const { calls } = stubRoutes(loadRoutes(dod4Configuration(), [MODEL_A, MODEL_B]));
    const state = new CharacterConfigState(CHARACTER_ID);

    await loadCharacterConfig(state);

    expect(calls).toHaveLength(2);
    expect(calls).toEqual(
      expect.arrayContaining([
        { method: "GET", path: CONFIG_PATH, search: "", body: undefined },
        { method: "GET", path: MODELS_PATH, search: "", body: undefined },
      ]),
    );
  });

  it("sets both statuses ready, holds both payloads as served and seeds an empty prompt draft — DoD-4", async () => {
    const served = dod4Configuration();
    stubRoutes(loadRoutes(served, [MODEL_A, MODEL_B]));
    const state = new CharacterConfigState(CHARACTER_ID);

    await expect(loadCharacterConfig(state)).resolves.toBeUndefined();

    expect(state.configStatus).toBe("ready");
    expect(state.modelsStatus).toBe("ready");
    expect(toJS(state.configuration)).toEqual(served);
    expect(toJS(state.models)).toEqual([MODEL_A, MODEL_B]);
    expect(state.promptDraft).toBe("");
    expect(state.savingKey).toBeNull();
    expect(state.failure).toBeNull();
  });

  it('model choices are "First enabled model", "A (S1)", "B (S2)" in order, with "A (S1)" selected — DoD-4', async () => {
    stubRoutes(loadRoutes(dod4Configuration(), [MODEL_A, MODEL_B]));
    const state = new CharacterConfigState(CHARACTER_ID);

    await loadCharacterConfig(state);

    const choices = modelChoices(state);
    expect(choices.map((choice) => choice.label)).toEqual([FIRST_ENABLED_MODEL, LABEL_A, LABEL_B]);
    expect(choices.map((choice) => choice.disabled)).toEqual([false, false, false]);
    expect(choices[0]?.value).toBe(UNSET_MODEL_VALUE);
    expect(choices[0]?.model).toBeNull();
    expect(choices[1]?.model).toEqual({ server_id: "7250000000000000301", model_name: "alpha-13b" });
    expect(choices[2]?.model).toEqual({ server_id: "7250000000000000302", model_name: "zeta-7b" });
    expect(new Set(choices.map((choice) => choice.value)).size).toBe(3);

    expect(selected(state)?.label).toBe(LABEL_A);
    expect(selectedModelValue(state)).not.toBe(UNSET_MODEL_VALUE);
  });

  it("the resolved-value lines read exactly the strings table's sentences — DoD-4", async () => {
    stubRoutes(loadRoutes(dod4Configuration(), [MODEL_A, MODEL_B]));
    const state = new CharacterConfigState(CHARACTER_ID);

    await loadCharacterConfig(state);
    const held = state.configuration;
    expect(held).not.toBeNull();
    if (held === null) return;

    expect(modelLine(held)).toBe(SET_HERE);
    expect(promptLine(held)).toBe(PROMPT_NOT_SET);
    expect(toolLine(held.tool_memo_search)).toBe(TOOL_DEFAULT);
    expect(toolLine(held.tool_session_search)).toBe(TOOL_OFF_HERE);
    expect(toolLine(held.tool_web_search)).toBe(TOOL_ON_HERE);
  });

  it("a set prompt seeds the draft verbatim and its line reads set here — DoD-4", async () => {
    const served = configuration({ system_prompt: "  Be Kestrel.\n" });
    stubRoutes(loadRoutes(served, [MODEL_A]));
    const state = new CharacterConfigState(CHARACTER_ID);

    await loadCharacterConfig(state);

    expect(state.promptDraft).toBe("  Be Kestrel.\n");
    expect(promptLine(configuration({ system_prompt: "  Be Kestrel.\n" }))).toBe(SET_HERE);
  });

  it("the tool lines map null / true / false to the three sentences — DoD-4", () => {
    expect(toolLine(null)).toBe("On (default)");
    expect(toolLine(true)).toBe("On (set on this character)");
    expect(toolLine(false)).toBe("Off (set on this character)");
  });

  it("the tool choice is Default / On / Off for null / true / false, and back for the patch value — DoD-4", () => {
    expect(toolChoice(null)).toBe("Default");
    expect(toolChoice(true)).toBe("On");
    expect(toolChoice(false)).toBe("Off");
    expect(toolPatchValue("Default")).toBeNull();
    expect(toolPatchValue("On")).toBe(true);
    expect(toolPatchValue("Off")).toBe(false);
  });
});

// ===========================================================================
describe("an unset model and a configured model that is not enabled", () => {
  it('a null model selects "First enabled model" and its line reads "Not set: …" — DoD-5', () => {
    const state = readyState(configuration({ model: null }), [MODEL_A, MODEL_B]);

    expect(selectedModelValue(state)).toBe(UNSET_MODEL_VALUE);
    expect(selected(state)?.label).toBe(FIRST_ENABLED_MODEL);
    expect(selected(state)?.disabled).toBe(false);
    expect(modelLine(configuration({ model: null }))).toBe(MODEL_NOT_SET);
    expect(modelChoices(state).map((choice) => choice.label)).toEqual([FIRST_ENABLED_MODEL, LABEL_A, LABEL_B]);
  });

  it('a null model loaded through the load effect selects "First enabled model" — DoD-5', async () => {
    stubRoutes(loadRoutes(configuration({ model: null }), [MODEL_B]));
    const state = new CharacterConfigState(CHARACTER_ID);

    await loadCharacterConfig(state);

    expect(selected(state)?.label).toBe(FIRST_ENABLED_MODEL);
    const held = state.configuration;
    expect(held === null ? null : modelLine(held)).toBe(MODEL_NOT_SET);
  });

  it('a configured model absent from [B] adds a disabled "A (not enabled)" choice, which is selected — DoD-5', () => {
    const state = readyState(configuration({ model: ref(MODEL_A) }), [MODEL_B]);

    const choices = modelChoices(state);
    expect(choices.slice(0, 2).map((choice) => choice.label)).toEqual([FIRST_ENABLED_MODEL, LABEL_B]);
    expect(choices).toHaveLength(3);
    const notEnabled = choices.filter((choice) => choice.label === LABEL_A_NOT_ENABLED);
    expect(notEnabled).toHaveLength(1);
    expect(notEnabled[0]?.disabled).toBe(true);
    expect(choices.filter((choice) => choice.disabled)).toHaveLength(1);
    expect(choices.some((choice) => choice.label === LABEL_A)).toBe(false);

    expect(selected(state)?.label).toBe(LABEL_A_NOT_ENABLED);
    expect(selected(state)?.disabled).toBe(true);
    expect(modelLine(configuration({ model: ref(MODEL_A) }))).toBe(SET_HERE);
  });

  it("the same model_name on another server_id counts as not enabled (both must match as strings) — DoD-5", () => {
    // alpha-13b is enabled on server 1 only; the character's model claims server 2.
    const state = readyState(
      configuration({ model: { server_id: SERVER_2, model_name: "alpha-13b" } }),
      [MODEL_A],
    );

    const choices = modelChoices(state);
    expect(choices.filter((choice) => choice.disabled).map((choice) => choice.label)).toEqual([
      LABEL_A_NOT_ENABLED,
    ]);
    expect(selected(state)?.label).toBe(LABEL_A_NOT_ENABLED);
  });

  it("a server_id differing only past double precision counts as not enabled — DoD-5", () => {
    // "…300" and "…301" parse to the same double; as strings they differ.
    const state = readyState(
      configuration({ model: { server_id: "7250000000000000300", model_name: "alpha-13b" } }),
      [MODEL_A],
    );

    expect(selected(state)?.label).toBe(LABEL_A_NOT_ENABLED);
    expect(selected(state)?.disabled).toBe(true);
  });

  it("a configured model that is enabled adds no disabled choice — DoD-5", () => {
    const state = readyState(configuration({ model: ref(MODEL_B) }), [MODEL_A, MODEL_B]);

    expect(modelChoices(state).some((choice) => choice.disabled)).toBe(false);
    expect(selected(state)?.label).toBe(LABEL_B);
  });
});

// ===========================================================================
describe("saveCharacterConfig saves one key, never optimistically", () => {
  it('{ tool_memo_search: false } PATCHes exactly {"tool_memo_search":false} — DoD-6', async () => {
    const served = configuration({ ...dod4Configuration(), tool_memo_search: false });
    const { calls, raws } = stubRoutes({ [`PATCH ${CONFIG_PATH}`]: () => jsonResponse(served, 200) });
    const state = readyState(dod4Configuration(), [MODEL_A, MODEL_B]);

    await expect(saveCharacterConfig(state, { tool_memo_search: false })).resolves.toBeUndefined();

    expect(calls).toEqual([
      { method: "PATCH", path: CONFIG_PATH, search: "", body: { tool_memo_search: false } },
    ]);
    expect(raws[0]).toBe('{"tool_memo_search":false}');
  });

  it("while pending the key is in flight, the held configuration is the old one, and a second save sends nothing — DoD-6", async () => {
    const pending = deferred<Response>();
    const { calls } = stubRoutes({ [`PATCH ${CONFIG_PATH}`]: () => pending.promise });
    const old = dod4Configuration();
    const state = readyState(old, [MODEL_A, MODEL_B]);

    const running = saveCharacterConfig(state, { tool_memo_search: false });
    await flush();

    expect(state.savingKey).toBe("tool_memo_search");
    expect(toJS(state.configuration)).toEqual(old);

    await expect(saveCharacterConfig(state, { tool_web_search: false })).resolves.toBeUndefined();
    await flush();
    expect(count(calls, "PATCH", CONFIG_PATH)).toBe(1);
    expect(calls[0]?.body).toEqual({ tool_memo_search: false });
    expect(state.savingKey).toBe("tool_memo_search");

    const served = configuration({ ...old, tool_memo_search: false });
    pending.resolve(jsonResponse(served, 200));
    await running;
    await flush();
    expect(count(calls, "PATCH", CONFIG_PATH)).toBe(1);
  });

  it("after the 200 the held configuration is the served one and nothing is in flight — DoD-6", async () => {
    // The served configuration differs beyond the saved key, so a merge would show.
    const served = configuration({
      model: ref(MODEL_B),
      system_prompt: null,
      tool_memo_search: false,
      tool_session_search: null,
      tool_web_search: null,
    });
    stubRoutes({ [`PATCH ${CONFIG_PATH}`]: () => jsonResponse(served, 200) });
    const state = readyState(dod4Configuration(), [MODEL_A, MODEL_B]);

    await saveCharacterConfig(state, { tool_memo_search: false });
    await flush();

    expect(toJS(state.configuration)).toEqual(served);
    expect(state.savingKey).toBeNull();
    expect(state.failure).toBeNull();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("the in-flight key is the patch's own key (model) — DoD-6", async () => {
    const pending = deferred<Response>();
    const { calls } = stubRoutes({ [`PATCH ${CONFIG_PATH}`]: () => pending.promise });
    const state = readyState(dod4Configuration(), [MODEL_A, MODEL_B]);

    const running = saveCharacterConfig(state, { model: null });
    await flush();

    expect(state.savingKey).toBe("model");
    expect(calls[0]?.body).toEqual({ model: null });

    pending.resolve(jsonResponse(configuration({ ...dod4Configuration(), model: null }), 200));
    await running;
    expect(state.savingKey).toBeNull();
    expect(state.configuration?.model).toBeNull();
  });

  it("a save clears an earlier failure as it starts — DoD-6", async () => {
    const pending = deferred<Response>();
    stubRoutes({ [`PATCH ${CONFIG_PATH}`]: () => pending.promise });
    const state = readyState(dod4Configuration(), [MODEL_A, MODEL_B]);
    runInAction(() => {
      state.failure = COULD_NOT_SAVE;
    });

    const running = saveCharacterConfig(state, { tool_web_search: false });
    await flush();
    expect(state.failure).toBeNull();

    pending.resolve(jsonResponse(configuration({ ...dod4Configuration(), tool_web_search: false }), 200));
    await running;
    expect(state.failure).toBeNull();
  });

  it("after the 200 the prompt draft follows the returned prompt — DoD-6", async () => {
    const served = configuration({ ...dod4Configuration(), system_prompt: "Served prompt." });
    stubRoutes({ [`PATCH ${CONFIG_PATH}`]: () => jsonResponse(served, 200) });
    const state = readyState(dod4Configuration(), [MODEL_A, MODEL_B]);

    await saveCharacterConfig(state, { system_prompt: "Served prompt." });

    expect(state.promptDraft).toBe("Served prompt.");
  });
});

// ===========================================================================
describe("saveCharacterConfig failures render inline (017 D10, D9)", () => {
  it('a 409 model_not_enabled sets "That model is no longer enabled." and keeps the held configuration — DoD-7', async () => {
    const old = dod4Configuration();
    stubRoutes({
      [`PATCH ${CONFIG_PATH}`]: () => notEnabledEnvelope(ref(MODEL_B)),
      [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: [MODEL_A] }, 200),
    });
    const state = readyState(old, [MODEL_A, MODEL_B]);

    await expect(saveCharacterConfig(state, { model: ref(MODEL_B) })).resolves.toBeUndefined();
    await flush();

    expect(state.failure).toBe(NO_LONGER_ENABLED);
    expect(toJS(state.configuration)).toEqual(old);
    expect(state.savingKey).toBeNull();
  });

  it("a 409 model_not_enabled then requests GET /api/models again — DoD-7", async () => {
    const { calls } = stubRoutes({
      [`PATCH ${CONFIG_PATH}`]: () => notEnabledEnvelope(ref(MODEL_B)),
      [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: [MODEL_A] }, 200),
    });
    const state = readyState(dod4Configuration(), [MODEL_A, MODEL_B]);

    await saveCharacterConfig(state, { model: ref(MODEL_B) });
    await flush();

    expect(calls.map((call) => `${call.method} ${call.path}${call.search}`)).toEqual([
      `PATCH ${CONFIG_PATH}`,
      `GET ${MODELS_PATH}`,
    ]);
  });

  it.each([
    ["a 500 envelope", () => envelope("internal_error", 500)],
    ["a 409 with another code", () => envelope("conflict", 409)],
    ["a 404 envelope", () => envelope("character_not_found", 404)],
    [
      "a transport failure",
      () => {
        throw new TypeError("Failed to fetch");
      },
    ],
  ] as [string, () => Response][])(
    '%s sets "Could not save the configuration.", keeps the held configuration and re-requests nothing — DoD-7',
    async (_label, answer) => {
      const old = dod4Configuration();
      const { calls } = stubRoutes({
        [`PATCH ${CONFIG_PATH}`]: () => answer(),
        [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: [MODEL_A] }, 200),
      });
      const state = readyState(old, [MODEL_A, MODEL_B]);

      await expect(saveCharacterConfig(state, { tool_session_search: true })).resolves.toBeUndefined();
      await flush();

      expect(state.failure).toBe(COULD_NOT_SAVE);
      expect(toJS(state.configuration)).toEqual(old);
      expect(state.savingKey).toBeNull();
      expect(calls.map((call) => `${call.method} ${call.path}`)).toEqual([`PATCH ${CONFIG_PATH}`]);
    },
  );

  it("neither failure calls notifyFailure, and both resolve without throwing — DoD-7", async () => {
    let answer: () => Response = () => notEnabledEnvelope(ref(MODEL_B));
    stubRoutes({
      [`PATCH ${CONFIG_PATH}`]: () => answer(),
      [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: [MODEL_A, MODEL_B] }, 200),
    });
    const state = readyState(dod4Configuration(), [MODEL_A, MODEL_B]);

    await expect(saveCharacterConfig(state, { model: ref(MODEL_B) })).resolves.toBeUndefined();
    await flush();
    expect(state.failure).toBe(NO_LONGER_ENABLED);

    answer = () => envelope("internal_error", 500);
    await expect(saveCharacterConfig(state, { tool_web_search: false })).resolves.toBeUndefined();
    await flush();
    expect(state.failure).toBe(COULD_NOT_SAVE);

    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
describe("commitPromptDraft saves the prompt on commit (017 D6, D9)", () => {
  it("an unchanged draft over a null prompt sends no request — DoD-8", async () => {
    const { calls } = stubRoutes({ [`PATCH ${CONFIG_PATH}`]: () => jsonResponse(configuration(), 200) });
    const state = readyState(configuration({ system_prompt: null }), [MODEL_A]);
    const before = snapshot(state);

    await expect(commitPromptDraft(state)).resolves.toBeUndefined();
    await flush();

    expect(calls).toEqual([]);
    expect(snapshot(state)).toEqual(before);
  });

  it("an unchanged draft over a set prompt sends no request — DoD-8", async () => {
    const { calls } = stubRoutes({
      [`PATCH ${CONFIG_PATH}`]: () => jsonResponse(configuration({ system_prompt: "Be terse." }), 200),
    });
    const state = readyState(configuration({ system_prompt: "Be terse." }), [MODEL_A]);
    setPromptDraft(state, "Be terse.");
    expect(state.promptDraft).toBe("Be terse.");

    await commitPromptDraft(state);
    await flush();

    expect(calls).toEqual([]);
  });

  it('a draft "  Be terse.\\n" PATCHes exactly {"system_prompt":"  Be terse.\\n"} (verbatim) — DoD-8', async () => {
    const served = configuration({ system_prompt: "  Be terse.\n" });
    const { calls, raws } = stubRoutes({ [`PATCH ${CONFIG_PATH}`]: () => jsonResponse(served, 200) });
    const state = readyState(configuration({ system_prompt: null }), [MODEL_A]);
    setPromptDraft(state, "  Be terse.\n");
    expect(state.promptDraft).toBe("  Be terse.\n");

    await expect(commitPromptDraft(state)).resolves.toBeUndefined();
    await flush();

    expect(calls).toEqual([
      { method: "PATCH", path: CONFIG_PATH, search: "", body: { system_prompt: "  Be terse.\n" } },
    ]);
    expect(raws[0]).toBe('{"system_prompt":"  Be terse.\\n"}');
    expect(state.configuration?.system_prompt).toBe("  Be terse.\n");
  });

  it('a whitespace-only draft over a set prompt PATCHes exactly {"system_prompt":null} — DoD-8', async () => {
    const served = configuration({ system_prompt: null });
    const { calls, raws } = stubRoutes({ [`PATCH ${CONFIG_PATH}`]: () => jsonResponse(served, 200) });
    const state = readyState(configuration({ system_prompt: "Be terse." }), [MODEL_A]);
    setPromptDraft(state, "  \n\t ");

    await commitPromptDraft(state);
    await flush();

    expect(calls).toEqual([
      { method: "PATCH", path: CONFIG_PATH, search: "", body: { system_prompt: null } },
    ]);
    expect(raws[0]).toBe('{"system_prompt":null}');
    expect(state.configuration?.system_prompt).toBeNull();
    expect(state.promptDraft).toBe("");
  });

  it("an empty draft over a set prompt PATCHes exactly {\"system_prompt\":null} — DoD-8", async () => {
    const { calls } = stubRoutes({
      [`PATCH ${CONFIG_PATH}`]: () => jsonResponse(configuration({ system_prompt: null }), 200),
    });
    const state = readyState(configuration({ system_prompt: "Be terse." }), [MODEL_A]);
    setPromptDraft(state, "");

    await commitPromptDraft(state);
    await flush();

    expect(calls.map((call) => call.body)).toEqual([{ system_prompt: null }]);
  });
});

// ===========================================================================
describe("the two loads are independent, and an aborted load writes nothing", () => {
  it.each(FAILURE_ANSWERS)(
    "a failed configuration load (%s) sets its status failed while the models load is ready — DoD-9",
    async (_label, answer) => {
      stubRoutes({
        [`GET ${CONFIG_PATH}`]: () => answer(),
        [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: [MODEL_A, MODEL_B] }, 200),
      });
      const state = new CharacterConfigState(CHARACTER_ID);

      await expect(loadCharacterConfig(state)).resolves.toBeUndefined();

      expect(state.configStatus).toBe("failed");
      expect(state.configuration).toBeNull();
      expect(state.modelsStatus).toBe("ready");
      expect(toJS(state.models)).toEqual([MODEL_A, MODEL_B]);
    },
  );

  it.each(FAILURE_ANSWERS)(
    "a failed models load (%s) sets its status failed while the configuration load is ready — DoD-9",
    async (_label, answer) => {
      const served = dod4Configuration();
      stubRoutes({
        [`GET ${CONFIG_PATH}`]: () => jsonResponse(served, 200),
        [`GET ${MODELS_PATH}`]: () => answer(),
      });
      const state = new CharacterConfigState(CHARACTER_ID);

      await expect(loadCharacterConfig(state)).resolves.toBeUndefined();

      expect(state.modelsStatus).toBe("failed");
      expect(toJS(state.models)).toEqual([]);
      expect(state.configStatus).toBe("ready");
      expect(toJS(state.configuration)).toEqual(served);
    },
  );

  it("never rejects when both loads fail, and both statuses are failed — DoD-9", async () => {
    stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => envelope("internal_error", 500),
      [`GET ${MODELS_PATH}`]: () => {
        throw new TypeError("Failed to fetch");
      },
    });
    const state = new CharacterConfigState(CHARACTER_ID);

    await expect(loadCharacterConfig(state)).resolves.toBeUndefined();

    expect(state.configStatus).toBe("failed");
    expect(state.modelsStatus).toBe("failed");
  });

  it("a retry after a failure shows loading while pending — DoD-9", async () => {
    const config = deferred<Response>();
    const models = deferred<Response>();
    stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => config.promise,
      [`GET ${MODELS_PATH}`]: () => models.promise,
    });
    const state = new CharacterConfigState(CHARACTER_ID);
    runInAction(() => {
      state.configStatus = "failed";
      state.modelsStatus = "failed";
    });

    const running = loadCharacterConfig(state);
    await flush();
    expect(state.configStatus).toBe("loading");
    expect(state.modelsStatus).toBe("loading");

    config.resolve(jsonResponse(dod4Configuration(), 200));
    models.resolve(jsonResponse({ models: [MODEL_A] }, 200));
    await running;
    expect(state.configStatus).toBe("ready");
    expect(state.modelsStatus).toBe("ready");
  });

  it("writes nothing when the responses arrive after the abort — DoD-9", async () => {
    const config = deferred<Response>();
    const models = deferred<Response>();
    stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => config.promise,
      [`GET ${MODELS_PATH}`]: () => models.promise,
    });
    const state = new CharacterConfigState(CHARACTER_ID);
    const controller = new AbortController();

    const running = loadCharacterConfig(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();
    config.resolve(jsonResponse(configuration({ system_prompt: "Late prompt." }), 200));
    models.resolve(jsonResponse({ models: [MODEL_A] }, 200));

    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
    expect(state.configuration).toBeNull();
    expect(toJS(state.models)).toEqual([]);
    expect(state.promptDraft).toBe("");
    expect(state.configStatus).not.toBe("ready");
    expect(state.modelsStatus).not.toBe("ready");
  });

  it("writes nothing when its signal aborts the pending requests — DoD-9", async () => {
    const hang: Handler = (_request, init) =>
      new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal;
        signal?.addEventListener("abort", () => {
          reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
        });
      });
    stubRoutes({ [`GET ${CONFIG_PATH}`]: hang, [`GET ${MODELS_PATH}`]: hang });
    const state = new CharacterConfigState(CHARACTER_ID);
    const controller = new AbortController();

    const running = loadCharacterConfig(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();

    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
    expect(state.configStatus).not.toBe("failed");
    expect(state.modelsStatus).not.toBe("failed");
  });

  it("an already-aborted signal writes nothing — DoD-9", async () => {
    stubRoutes(loadRoutes(dod4Configuration(), [MODEL_A, MODEL_B]));
    const state = new CharacterConfigState(CHARACTER_ID);
    const before = snapshot(state);
    const controller = new AbortController();
    controller.abort();

    await expect(loadCharacterConfig(state, controller.signal)).resolves.toBeUndefined();
    await flush();

    expect(state.configuration).toBeNull();
    expect(toJS(state.models)).toEqual([]);
    expect(state.promptDraft).toBe(before.promptDraft);
    expect(state.configStatus).not.toBe("ready");
    expect(state.configStatus).not.toBe("failed");
    expect(state.modelsStatus).not.toBe("ready");
    expect(state.modelsStatus).not.toBe("failed");
  });
});
