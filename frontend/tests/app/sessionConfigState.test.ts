// Feature 017, step 008 — the session configuration state (DoD-1..DoD-8).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 008.context.md ("Why two statuses", "Branch on `.code` only", "Mutation posture", "Test
// notes") and context.md: the Wire contract (`GET /api/models`, `GET` / `PATCH
// /api/sessions/{id}/configuration`, the 409 `model_not_enabled` envelope), D2's check order,
// D10, D17 (unknown never blocks), D19 (no notification) and the UI strings table:
//   - picker failures: "That model is no longer enabled." / "Could not change the model.";
//   - gate reasons: "Cannot send: no model is enabled on this instance." /
//     "Cannot send: choose a model for this session." /
//     "Cannot send: this session's model is not enabled. Choose another model."
// Expected sentences are literals from the strings table, never computed by calling
// sendBlockedReason. Requests are stubbed and recorded by exact method + pathname + query.
import { autorun, runInAction, toJS } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EnabledModel, ModelRef, SessionConfiguration, Setting } from "../../src/app/configurationApi";
import {
  SessionConfigState,
  applySessionConfiguration,
  chooseModel,
  loadSessionConfig,
  modelUsability,
  sameModel,
  sendBlockedReason,
} from "../../src/app/sessionConfigState";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };
type Handler = (request: Seen, init?: RequestInit) => Response | Promise<Response>;

// ---------------------------------------------------------------- the spec's names
const SESSION_ID = "s1";
const CONFIG_PATH = "/api/sessions/s1/configuration";
const MODELS_PATH = "/api/models";

const NO_LONGER_ENABLED = "That model is no longer enabled.";
const COULD_NOT_CHANGE = "Could not change the model.";
const REASON_NO_MODEL_ENABLED = "Cannot send: no model is enabled on this instance.";
const REASON_NOT_CHOSEN = "Cannot send: choose a model for this session.";
const REASON_NOT_ENABLED = "Cannot send: this session's model is not enabled. Choose another model.";

// ---------------------------------------------------------------- payload builders
const SERVER_A = "7250000000000000301";
const SERVER_B = "7250000000000000302";

function enabled(server_id: string, server_name: string, model_name: string): EnabledModel {
  return { server_id, server_name, model_name };
}

// Served order deliberately not sorted by server_id or name, so a reorder would show.
const MODEL_B_ZETA = enabled(SERVER_B, "Box Two", "zeta-7b");
const MODEL_A_ALPHA = enabled(SERVER_A, "Box One", "alpha-13b");
const MODEL_A_MID = enabled(SERVER_A, "Box One", "mid-8b");
const MODELS: EnabledModel[] = [MODEL_B_ZETA, MODEL_A_ALPHA, MODEL_A_MID];

function ref(model: EnabledModel): ModelRef {
  return { server_id: model.server_id, model_name: model.model_name };
}

function textSetting(session: string | null, inherited: string | null): Setting<string> {
  const value = session ?? inherited;
  return {
    session,
    inherited,
    inherited_level: inherited === null ? null : "character",
    value,
    level: session !== null ? "session" : inherited !== null ? "character" : null,
  };
}

function languageSetting(session: string | null, inherited: string | null): Setting<string> {
  return {
    session,
    inherited,
    inherited_level: inherited === null ? null : "user",
    value: session ?? inherited,
    level: session !== null ? "session" : inherited !== null ? "user" : null,
  };
}

function toolSetting(session: boolean | null): Setting<boolean> {
  return {
    session,
    inherited: true,
    inherited_level: "default",
    value: session ?? true,
    level: session !== null ? "session" : "default",
  };
}

function configuration(model: ModelRef | null, prompt: string | null = "Be Kestrel."): SessionConfiguration {
  return {
    model: model === null ? null : { ...model },
    system_prompt: textSetting(null, prompt),
    tool_memo_search: toolSetting(null),
    tool_session_search: toolSetting(false),
    tool_web_search: toolSetting(null),
    rp_language: languageSetting(null, "Japanese"),
    preferred_language: languageSetting("English", null),
  };
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
    level: "session",
  });
}

type Routes = Record<string, (request: Seen, init?: RequestInit) => Response | Promise<Response>>;

/** Answers by exact `METHOD path?query`; anything else is a 500 and is still recorded, so the
 * request-log assertions catch a stray call. */
function stubRoutes(routes: Routes) {
  return stubBackend((request, init) => {
    const key = `${request.method} ${request.path}${request.search}`;
    const answer = routes[key];
    if (answer === undefined) return envelope("unexpected_request", 500);
    return answer(request, init);
  });
}

function stubBackend(handler: Handler) {
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
    return handler(request, init);
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

function snapshot(state: SessionConfigState) {
  return {
    sessionId: state.sessionId,
    configuration: state.configuration === null ? null : toJS(state.configuration),
    configStatus: state.configStatus,
    modelsStatus: state.modelsStatus,
    models: state.models.map((model) => ({ ...model })),
    modelSaving: state.modelSaving,
    modelFailure: state.modelFailure,
  };
}

/** A state as a successful load leaves it: both ready, `configuration` and `models` set. */
function readyState(config: SessionConfiguration, models: EnabledModel[]): SessionConfigState {
  const state = new SessionConfigState(SESSION_ID);
  runInAction(() => {
    state.configuration = structuredClone(config);
    state.models = models.map((model) => ({ ...model }));
    state.configStatus = "ready";
    state.modelsStatus = "ready";
  });
  return state;
}

function count(calls: Seen[], method: string, path: string): number {
  return calls.filter((call) => call.method === method && call.path === path).length;
}

const FAILURE_ANSWERS: [label: string, answer: () => Response][] = [
  ["a 500 envelope", () => envelope("internal_error", 500)],
  ["a 404 envelope", () => envelope("session_not_found", 404)],
  [
    "a transport failure",
    () => {
      throw new TypeError("Failed to fetch");
    },
  ],
];

// ===========================================================================
describe("a fresh SessionConfigState", () => {
  it('has configuration null, both statuses "idle", no models, not saving and no failure — DoD-1', () => {
    const state = new SessionConfigState("s1");

    expect(snapshot(state)).toEqual({
      sessionId: "s1",
      configuration: null,
      configStatus: "idle",
      modelsStatus: "idle",
      models: [],
      modelSaving: false,
      modelFailure: null,
    });
  });
});

// ===========================================================================
describe("loadSessionConfig loads the configuration and the enabled models", () => {
  it("requests exactly GET /api/sessions/s1/configuration and GET /api/models — DoD-2", async () => {
    const { calls } = stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => jsonResponse(configuration(ref(MODEL_A_ALPHA)), 200),
      [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: MODELS }, 200),
    });
    const state = new SessionConfigState(SESSION_ID);

    await loadSessionConfig(state);

    expect(calls).toHaveLength(2);
    expect(calls).toEqual(
      expect.arrayContaining([
        { method: "GET", path: CONFIG_PATH, search: "", body: undefined },
        { method: "GET", path: MODELS_PATH, search: "", body: undefined },
      ]),
    );
  });

  it("issues both requests before either answers (in parallel) — DoD-2", async () => {
    const config = deferred<Response>();
    const models = deferred<Response>();
    const { calls } = stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => config.promise,
      [`GET ${MODELS_PATH}`]: () => models.promise,
    });
    const state = new SessionConfigState(SESSION_ID);

    const running = loadSessionConfig(state);
    await flush();
    expect(count(calls, "GET", CONFIG_PATH)).toBe(1);
    expect(count(calls, "GET", MODELS_PATH)).toBe(1);
    expect(state.configStatus).toBe("loading");
    expect(state.modelsStatus).toBe("loading");

    config.resolve(jsonResponse(configuration(null), 200));
    models.resolve(jsonResponse({ models: MODELS }, 200));
    await running;
  });

  it("becomes ready with both payloads as served, model order and id strings unchanged — DoD-2", async () => {
    const served = configuration(ref(MODEL_A_MID));
    stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => jsonResponse(served, 200),
      [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: MODELS }, 200),
    });
    const state = new SessionConfigState(SESSION_ID);

    await expect(loadSessionConfig(state)).resolves.toBeUndefined();

    expect(state.configStatus).toBe("ready");
    expect(state.modelsStatus).toBe("ready");
    expect(state.configuration).toEqual(served);
    expect(state.models).toEqual([
      { server_id: "7250000000000000302", server_name: "Box Two", model_name: "zeta-7b" },
      { server_id: "7250000000000000301", server_name: "Box One", model_name: "alpha-13b" },
      { server_id: "7250000000000000301", server_name: "Box One", model_name: "mid-8b" },
    ]);
    for (const model of state.models) expect(typeof model.server_id).toBe("string");
    expect(state.configuration?.model).toEqual({ server_id: "7250000000000000301", model_name: "mid-8b" });
  });

  it("an empty models list loads as ready with no models — DoD-2", async () => {
    stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => jsonResponse(configuration(null), 200),
      [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: [] }, 200),
    });
    const state = new SessionConfigState(SESSION_ID);

    await loadSessionConfig(state);

    expect(state.modelsStatus).toBe("ready");
    expect(state.models).toEqual([]);
    expect(state.configStatus).toBe("ready");
  });

  it.each(FAILURE_ANSWERS)(
    'when only the models request fails (%s) modelsStatus is "failed" and configStatus "ready" — DoD-2',
    async (_label, answer) => {
      const served = configuration(ref(MODEL_A_ALPHA));
      stubRoutes({
        [`GET ${CONFIG_PATH}`]: () => jsonResponse(served, 200),
        [`GET ${MODELS_PATH}`]: () => answer(),
      });
      const state = new SessionConfigState(SESSION_ID);

      await expect(loadSessionConfig(state)).resolves.toBeUndefined();

      expect(state.modelsStatus).toBe("failed");
      expect(state.models).toEqual([]);
      expect(state.configStatus).toBe("ready");
      expect(state.configuration).toEqual(served);
    },
  );

  it.each(FAILURE_ANSWERS)(
    'when only the configuration request fails (%s) configStatus is "failed" and modelsStatus "ready" — DoD-2',
    async (_label, answer) => {
      stubRoutes({
        [`GET ${CONFIG_PATH}`]: () => answer(),
        [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: MODELS }, 200),
      });
      const state = new SessionConfigState(SESSION_ID);

      await expect(loadSessionConfig(state)).resolves.toBeUndefined();

      expect(state.configStatus).toBe("failed");
      expect(state.configuration).toBeNull();
      expect(state.modelsStatus).toBe("ready");
      expect(state.models).toEqual(MODELS);
    },
  );

  it("never rejects when both requests fail, and both statuses are failed — DoD-2", async () => {
    stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => envelope("internal_error", 500),
      [`GET ${MODELS_PATH}`]: () => {
        throw new TypeError("Failed to fetch");
      },
    });
    const state = new SessionConfigState(SESSION_ID);

    await expect(loadSessionConfig(state)).resolves.toBeUndefined();

    expect(state.configStatus).toBe("failed");
    expect(state.modelsStatus).toBe("failed");
  });

  it("a failed reload keeps each request's previous data — DoD-2", async () => {
    const previous = configuration(ref(MODEL_A_ALPHA));
    stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => envelope("internal_error", 500),
      [`GET ${MODELS_PATH}`]: () => envelope("internal_error", 500),
    });
    const state = readyState(previous, MODELS);

    await expect(loadSessionConfig(state)).resolves.toBeUndefined();

    expect(state.configStatus).toBe("failed");
    expect(state.modelsStatus).toBe("failed");
    expect(state.configuration).toEqual(previous);
    expect(state.models).toEqual(MODELS);
  });

  it("writes nothing when its signal aborts before the responses settle — DoD-2", async () => {
    const hang = (_request: Seen, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal;
        signal?.addEventListener("abort", () => {
          reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
        });
      });
    stubRoutes({ [`GET ${CONFIG_PATH}`]: hang, [`GET ${MODELS_PATH}`]: hang });
    const state = new SessionConfigState(SESSION_ID);
    const controller = new AbortController();

    const running = loadSessionConfig(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();

    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
    expect(state.configStatus).not.toBe("failed");
    expect(state.modelsStatus).not.toBe("failed");
  });

  it("writes nothing when the responses arrive after the abort — DoD-2", async () => {
    const config = deferred<Response>();
    const models = deferred<Response>();
    stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => config.promise,
      [`GET ${MODELS_PATH}`]: () => models.promise,
    });
    const state = new SessionConfigState(SESSION_ID);
    const controller = new AbortController();

    const running = loadSessionConfig(state, controller.signal);
    await flush();
    const atAbort = snapshot(state);
    controller.abort();
    config.resolve(jsonResponse(configuration(ref(MODEL_A_ALPHA)), 200));
    models.resolve(jsonResponse({ models: MODELS }, 200));

    await expect(running).resolves.toBeUndefined();
    await flush();
    expect(snapshot(state)).toEqual(atAbort);
    expect(state.configuration).toBeNull();
    expect(state.models).toEqual([]);
    expect(state.configStatus).not.toBe("ready");
    expect(state.modelsStatus).not.toBe("ready");
  });

  it("an already-aborted signal writes nothing — DoD-2", async () => {
    stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => jsonResponse(configuration(ref(MODEL_A_ALPHA)), 200),
      [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: MODELS }, 200),
    });
    const state = new SessionConfigState(SESSION_ID);
    const controller = new AbortController();
    controller.abort();

    await expect(loadSessionConfig(state, controller.signal)).resolves.toBeUndefined();
    await flush();

    expect(state.configuration).toBeNull();
    expect(state.models).toEqual([]);
    expect(state.configStatus).not.toBe("ready");
    expect(state.configStatus).not.toBe("failed");
    expect(state.modelsStatus).not.toBe("ready");
    expect(state.modelsStatus).not.toBe("failed");
  });
});

// ===========================================================================
describe("sameModel compares server_id and model_name as strings", () => {
  it("is true when both server_id and model_name are equal — DoD-3", () => {
    expect(
      sameModel(
        { server_id: "7250000000000000301", model_name: "alpha-13b" },
        { server_id: "7250000000000000301", model_name: "alpha-13b" },
      ),
    ).toBe(true);
  });

  it("is false for the same name on a different server_id — DoD-3", () => {
    expect(
      sameModel(
        { server_id: "7250000000000000301", model_name: "alpha-13b" },
        { server_id: "7250000000000000302", model_name: "alpha-13b" },
      ),
    ).toBe(false);
  });

  it("is false for the same server_id with a different model_name — DoD-3", () => {
    expect(
      sameModel(
        { server_id: "7250000000000000301", model_name: "alpha-13b" },
        { server_id: "7250000000000000301", model_name: "mid-8b" },
      ),
    ).toBe(false);
  });

  it("compares ids as strings, never as numbers (no precision loss) — DoD-3", () => {
    // Both parse to the same double; as strings they differ.
    expect(
      sameModel(
        { server_id: "7250000000000000301", model_name: "alpha-13b" },
        { server_id: "7250000000000000300", model_name: "alpha-13b" },
      ),
    ).toBe(false);
  });
});

// ===========================================================================
describe("modelUsability and sendBlockedReason with both loaded (D2 order, D17)", () => {
  it('empty models → "no_model_enabled" with its sentence, even when the captured model is set — DoD-3', () => {
    const state = readyState(configuration(ref(MODEL_A_ALPHA)), []);

    expect(modelUsability(state)).toBe("no_model_enabled");
    expect(sendBlockedReason(state)).toBe(REASON_NO_MODEL_ENABLED);
  });

  it('empty models with no captured model → "no_model_enabled" (outranks not chosen) — DoD-3', () => {
    const state = readyState(configuration(null), []);

    expect(modelUsability(state)).toBe("no_model_enabled");
    expect(sendBlockedReason(state)).toBe(REASON_NO_MODEL_ENABLED);
  });

  it('models present and captured null → "not_chosen" with its sentence — DoD-3', () => {
    const state = readyState(configuration(null), MODELS);

    expect(modelUsability(state)).toBe("not_chosen");
    expect(sendBlockedReason(state)).toBe(REASON_NOT_CHOSEN);
  });

  it('captured model absent from the list → "not_enabled" with its sentence — DoD-3', () => {
    const state = readyState(
      configuration({ server_id: "7250000000000000399", model_name: "gone-70b" }),
      MODELS,
    );

    expect(modelUsability(state)).toBe("not_enabled");
    expect(sendBlockedReason(state)).toBe(REASON_NOT_ENABLED);
  });

  it('same model_name on a different server_id counts as absent → "not_enabled" — DoD-3', () => {
    // alpha-13b is listed on SERVER_A only; the captured one claims SERVER_B.
    const state = readyState(configuration({ server_id: SERVER_B, model_name: "alpha-13b" }), MODELS);

    expect(modelUsability(state)).toBe("not_enabled");
    expect(sendBlockedReason(state)).toBe(REASON_NOT_ENABLED);
  });

  it.each([
    ["the first listed", MODEL_B_ZETA],
    ["a later listed", MODEL_A_MID],
  ])('captured model is %s model → "usable", reason null — DoD-3', (_label, model) => {
    const state = readyState(configuration(ref(model)), MODELS);

    expect(modelUsability(state)).toBe("usable");
    expect(sendBlockedReason(state)).toBeNull();
  });
});

// ===========================================================================
describe("unknown never blocks (D17)", () => {
  const STATUS_CASES = [
    ["idle", "idle"],
    ["loading", "ready"],
    ["ready", "loading"],
    ["loading", "loading"],
    ["failed", "ready"],
    ["ready", "failed"],
    ["failed", "failed"],
    ["idle", "ready"],
    ["ready", "idle"],
  ] as const;

  it.each(STATUS_CASES)(
    'configStatus "%s" / modelsStatus "%s" → "unknown", reason null, even with an empty list — DoD-4',
    (configStatus, modelsStatus) => {
      const state = readyState(configuration(ref(MODEL_A_ALPHA)), []);
      runInAction(() => {
        state.configStatus = configStatus;
        state.modelsStatus = modelsStatus;
      });

      expect(modelUsability(state)).toBe("unknown");
      expect(sendBlockedReason(state)).toBeNull();
    },
  );

  it("a fresh state is unknown and unblocked — DoD-4", () => {
    const state = new SessionConfigState(SESSION_ID);

    expect(modelUsability(state)).toBe("unknown");
    expect(sendBlockedReason(state)).toBeNull();
  });

  it("while the models request is pending after the configuration loaded, usability is unknown — DoD-4", async () => {
    const models = deferred<Response>();
    stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => jsonResponse(configuration(null), 200),
      [`GET ${MODELS_PATH}`]: () => models.promise,
    });
    const state = new SessionConfigState(SESSION_ID);

    const running = loadSessionConfig(state);
    await flush();
    expect(state.configStatus).toBe("ready");
    expect(modelUsability(state)).toBe("unknown");
    expect(sendBlockedReason(state)).toBeNull();

    models.resolve(jsonResponse({ models: MODELS }, 200));
    await running;
  });

  it("while the configuration request is pending after an empty models list loaded, usability is unknown — DoD-4", async () => {
    const config = deferred<Response>();
    stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => config.promise,
      [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: [] }, 200),
    });
    const state = new SessionConfigState(SESSION_ID);

    const running = loadSessionConfig(state);
    await flush();
    expect(state.modelsStatus).toBe("ready");
    expect(modelUsability(state)).toBe("unknown");
    expect(sendBlockedReason(state)).toBeNull();

    config.resolve(jsonResponse(configuration(null), 200));
    await running;
  });

  it("after a failed models load, usability is unknown and the reason null — DoD-4", async () => {
    stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => jsonResponse(configuration(null), 200),
      [`GET ${MODELS_PATH}`]: () => envelope("internal_error", 500),
    });
    const state = new SessionConfigState(SESSION_ID);

    await loadSessionConfig(state);

    expect(state.modelsStatus).toBe("failed");
    expect(modelUsability(state)).toBe("unknown");
    expect(sendBlockedReason(state)).toBeNull();
  });

  it("after a failed configuration load, usability is unknown and the reason null — DoD-4", async () => {
    stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => envelope("internal_error", 500),
      [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: [] }, 200),
    });
    const state = new SessionConfigState(SESSION_ID);

    await loadSessionConfig(state);

    expect(state.configStatus).toBe("failed");
    expect(modelUsability(state)).toBe("unknown");
    expect(sendBlockedReason(state)).toBeNull();
  });
});

// ===========================================================================
describe("chooseModel changes the captured model, never optimistically (US-105.AC-1)", () => {
  it('PATCHes /api/sessions/s1/configuration with exactly {"model":{"server_id":…,"model_name":…}} — DoD-5', async () => {
    const served = configuration(ref(MODEL_A_MID));
    const { calls, raws } = stubRoutes({
      [`PATCH ${CONFIG_PATH}`]: () => jsonResponse(served, 200),
    });
    const state = readyState(configuration(ref(MODEL_A_ALPHA)), MODELS);

    await expect(chooseModel(state, ref(MODEL_A_MID))).resolves.toBeUndefined();

    expect(calls).toEqual([
      {
        method: "PATCH",
        path: CONFIG_PATH,
        search: "",
        body: { model: { server_id: "7250000000000000301", model_name: "mid-8b" } },
      },
    ]);
    expect(raws[0]).toBe('{"model":{"server_id":"7250000000000000301","model_name":"mid-8b"}}');
  });

  it("while pending modelSaving is true and configuration.model is still the old one — DoD-5", async () => {
    const pending = deferred<Response>();
    stubRoutes({ [`PATCH ${CONFIG_PATH}`]: () => pending.promise });
    const state = readyState(configuration(ref(MODEL_A_ALPHA)), MODELS);

    const running = chooseModel(state, ref(MODEL_B_ZETA));
    await flush();

    expect(state.modelSaving).toBe(true);
    expect(state.configuration?.model).toEqual({ server_id: SERVER_A, model_name: "alpha-13b" });

    pending.resolve(jsonResponse(configuration(ref(MODEL_B_ZETA)), 200));
    await running;
  });

  it("after the response configuration is the served one and saving is over — DoD-5", async () => {
    // The served configuration differs from the old one beyond the model, so a merge would show.
    const served = configuration(ref(MODEL_B_ZETA), "A served prompt.");
    stubRoutes({ [`PATCH ${CONFIG_PATH}`]: () => jsonResponse(served, 200) });
    const state = readyState(configuration(ref(MODEL_A_ALPHA)), MODELS);

    await chooseModel(state, ref(MODEL_B_ZETA));
    await flush();

    expect(state.configuration).toEqual(served);
    expect(state.modelSaving).toBe(false);
    expect(state.modelFailure).toBeNull();
    expect(modelUsability(state)).toBe("usable");
  });

  it("a successful change clears an earlier failure — DoD-5", async () => {
    stubRoutes({ [`PATCH ${CONFIG_PATH}`]: () => jsonResponse(configuration(ref(MODEL_A_MID)), 200) });
    const state = readyState(configuration(ref(MODEL_A_ALPHA)), MODELS);
    runInAction(() => {
      state.modelFailure = COULD_NOT_CHANGE;
    });

    await chooseModel(state, ref(MODEL_A_MID));

    expect(state.modelFailure).toBeNull();
  });

  it("choosing a model when none is captured sends the PATCH — DoD-5", async () => {
    const { calls } = stubRoutes({
      [`PATCH ${CONFIG_PATH}`]: () => jsonResponse(configuration(ref(MODEL_A_ALPHA)), 200),
    });
    const state = readyState(configuration(null), MODELS);

    await chooseModel(state, ref(MODEL_A_ALPHA));

    expect(calls.map((call) => call.body)).toEqual([
      { model: { server_id: SERVER_A, model_name: "alpha-13b" } },
    ]);
    expect(state.configuration?.model).toEqual({ server_id: SERVER_A, model_name: "alpha-13b" });
  });
});

// ===========================================================================
describe("chooseModel failures render inline (D10, D19)", () => {
  const REREAD = [enabled(SERVER_A, "Box One", "mid-8b")];

  it('a 409 model_not_enabled sets "That model is no longer enabled." and keeps the previous configuration — DoD-6', async () => {
    const previous = configuration(ref(MODEL_A_ALPHA));
    stubRoutes({
      [`PATCH ${CONFIG_PATH}`]: () => notEnabledEnvelope(ref(MODEL_B_ZETA)),
      [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: REREAD }, 200),
    });
    const state = readyState(previous, MODELS);

    await expect(chooseModel(state, ref(MODEL_B_ZETA))).resolves.toBeUndefined();
    await flush();

    expect(state.modelFailure).toBe(NO_LONGER_ENABLED);
    expect(state.configuration).toEqual(previous);
    expect(state.modelSaving).toBe(false);
  });

  it("a 409 model_not_enabled then requests GET /api/models again and takes the re-read list — DoD-6", async () => {
    const { calls } = stubRoutes({
      [`PATCH ${CONFIG_PATH}`]: () => notEnabledEnvelope(ref(MODEL_B_ZETA)),
      [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: REREAD }, 200),
    });
    const state = readyState(configuration(ref(MODEL_A_ALPHA)), MODELS);

    await chooseModel(state, ref(MODEL_B_ZETA));
    await flush();

    expect(calls.map((call) => `${call.method} ${call.path}${call.search}`)).toEqual([
      `PATCH ${CONFIG_PATH}`,
      `GET ${MODELS_PATH}`,
    ]);
    expect(state.models).toEqual(REREAD);
  });

  it.each([
    ["a 500 envelope", () => envelope("internal_error", 500)],
    ["a 409 with another code", () => envelope("conflict", 409)],
    ["a 422 envelope", () => envelope("validation_error", 422)],
    [
      "a transport failure",
      () => {
        throw new TypeError("Failed to fetch");
      },
    ],
  ] as [string, () => Response][])(
    '%s sets "Could not change the model.", keeps the configuration and re-reads nothing — DoD-6',
    async (_label, answer) => {
      const previous = configuration(ref(MODEL_A_ALPHA));
      const { calls } = stubRoutes({
        [`PATCH ${CONFIG_PATH}`]: () => answer(),
        [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: REREAD }, 200),
      });
      const state = readyState(previous, MODELS);

      await expect(chooseModel(state, ref(MODEL_B_ZETA))).resolves.toBeUndefined();
      await flush();

      expect(state.modelFailure).toBe(COULD_NOT_CHANGE);
      expect(state.configuration).toEqual(previous);
      expect(state.models).toEqual(MODELS);
      expect(state.modelSaving).toBe(false);
      expect(calls.map((call) => `${call.method} ${call.path}`)).toEqual([`PATCH ${CONFIG_PATH}`]);
    },
  );

  it("neither failure path calls notifyFailure — DoD-6", async () => {
    let answer: () => Response = () => notEnabledEnvelope(ref(MODEL_B_ZETA));
    stubRoutes({
      [`PATCH ${CONFIG_PATH}`]: () => answer(),
      [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: MODELS }, 200),
    });
    const state = readyState(configuration(ref(MODEL_A_ALPHA)), MODELS);

    await expect(chooseModel(state, ref(MODEL_B_ZETA))).resolves.toBeUndefined();
    await flush();
    answer = () => envelope("internal_error", 500);
    await expect(chooseModel(state, ref(MODEL_B_ZETA))).resolves.toBeUndefined();
    await flush();

    expect(state.modelFailure).toBe(COULD_NOT_CHANGE);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
describe("chooseModel ignores a no-op or overlapping change", () => {
  it("with the currently captured model it sends nothing — DoD-7", async () => {
    const { calls } = stubRoutes({
      [`PATCH ${CONFIG_PATH}`]: () => jsonResponse(configuration(ref(MODEL_A_ALPHA)), 200),
    });
    const state = readyState(configuration(ref(MODEL_A_ALPHA)), MODELS);
    const before = snapshot(state);

    // A fresh object equal by value, not the same reference.
    await expect(
      chooseModel(state, { server_id: "7250000000000000301", model_name: "alpha-13b" }),
    ).resolves.toBeUndefined();
    await flush();

    expect(calls).toEqual([]);
    expect(snapshot(state)).toEqual(before);
  });

  it("while another change is in flight it sends nothing — DoD-7", async () => {
    const pending = deferred<Response>();
    const { calls } = stubRoutes({ [`PATCH ${CONFIG_PATH}`]: () => pending.promise });
    const state = readyState(configuration(ref(MODEL_A_ALPHA)), MODELS);

    const first = chooseModel(state, ref(MODEL_B_ZETA));
    await flush();
    expect(state.modelSaving).toBe(true);

    await expect(chooseModel(state, ref(MODEL_A_MID))).resolves.toBeUndefined();
    await flush();
    expect(count(calls, "PATCH", CONFIG_PATH)).toBe(1);
    expect(calls[0]?.body).toEqual({ model: { server_id: SERVER_B, model_name: "zeta-7b" } });

    pending.resolve(jsonResponse(configuration(ref(MODEL_B_ZETA)), 200));
    await first;
    await flush();
    expect(count(calls, "PATCH", CONFIG_PATH)).toBe(1);
    expect(state.configuration?.model).toEqual({ server_id: SERVER_B, model_name: "zeta-7b" });
  });
});

// ===========================================================================
describe("applySessionConfiguration and reactivity", () => {
  it("applySessionConfiguration replaces configuration — DoD-8", () => {
    const state = readyState(configuration(ref(MODEL_A_ALPHA)), MODELS);
    const saved = configuration(ref(MODEL_A_ALPHA), "The modal's saved prompt.");
    saved.tool_web_search = toolSetting(false);

    applySessionConfiguration(state, saved);

    expect(state.configuration).toEqual(saved);
  });

  it("applySessionConfiguration on a fresh state sets configuration — DoD-8", () => {
    const state = new SessionConfigState(SESSION_ID);
    const saved = configuration(null);

    applySessionConfiguration(state, saved);

    expect(state.configuration).toEqual(saved);
  });

  it("an autorun reading sendBlockedReason re-runs after loadSessionConfig settles — DoD-8", async () => {
    stubRoutes({
      [`GET ${CONFIG_PATH}`]: () => jsonResponse(configuration(null), 200),
      [`GET ${MODELS_PATH}`]: () => jsonResponse({ models: MODELS }, 200),
    });
    const state = new SessionConfigState(SESSION_ID);
    const seen: (string | null)[] = [];
    const dispose = autorun(() => {
      seen.push(sendBlockedReason(state));
    });

    try {
      expect(seen).toEqual([null]);
      await loadSessionConfig(state);
      await flush();

      expect(seen.length).toBeGreaterThan(1);
      expect(seen[seen.length - 1]).toBe(REASON_NOT_CHOSEN);
    } finally {
      dispose();
    }
  });

  it("an autorun reading sendBlockedReason re-runs after a chooseModel success — DoD-8", async () => {
    stubRoutes({
      [`PATCH ${CONFIG_PATH}`]: () => jsonResponse(configuration(ref(MODEL_A_ALPHA)), 200),
    });
    const state = readyState(configuration(null), MODELS);
    const seen: (string | null)[] = [];
    const dispose = autorun(() => {
      seen.push(sendBlockedReason(state));
    });

    try {
      expect(seen).toEqual([REASON_NOT_CHOSEN]);
      await chooseModel(state, ref(MODEL_A_ALPHA));
      await flush();

      expect(seen.length).toBeGreaterThan(1);
      expect(seen[seen.length - 1]).toBeNull();
    } finally {
      dispose();
    }
  });

  it("an autorun reading sendBlockedReason re-runs after applySessionConfiguration — DoD-8", () => {
    const state = readyState(configuration(ref(MODEL_A_ALPHA)), MODELS);
    const seen: (string | null)[] = [];
    const dispose = autorun(() => {
      seen.push(sendBlockedReason(state));
    });

    try {
      expect(seen).toEqual([null]);
      applySessionConfiguration(state, configuration({ server_id: SERVER_B, model_name: "alpha-13b" }));

      expect(seen[seen.length - 1]).toBe(REASON_NOT_ENABLED);
    } finally {
      dispose();
    }
  });
});
