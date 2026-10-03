// Feature 017, step 006 — the configuration API module (DoD-1..DoD-6).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 006.context.md and context.md's "Wire contract", D7 (server order), D10 (model_not_enabled
// detail), D18 (a patch carries exactly the keys it holds), D20 (no character call) and the
// "Ids are strings" constraint. Requests are matched by exact pathname, query and method.
// Every id used here is beyond Number.MAX_SAFE_INTEGER, so a numeric coercion would change it.
import { afterEach, describe, expect, it, vi } from "vitest";
import { isApiError } from "../../src/shared/apiError";
import * as configurationApi from "../../src/app/configurationApi";
import {
  type EnabledModel,
  fetchEnabledModels,
  fetchSessionConfiguration,
  fetchUserSettings,
  type SessionConfiguration,
  type Setting,
  updateSessionConfiguration,
  updateUserSettings,
  type UserSettings,
} from "../../src/app/configurationApi";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const SESSION_ID = "7250000000000000101";
const OTHER_SESSION_ID = "7250000000000000109";
const SERVER_A = "7250000000000000301";
const SERVER_B = "7250000000000000302";

const SESSION_CONFIG_PATH = `/api/sessions/${SESSION_ID}/configuration`;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- payload builders

function enabledModel(serverId: string, serverName: string, modelName: string): EnabledModel {
  return { server_id: serverId, server_name: serverName, model_name: modelName };
}

function textSetting(overrides: Partial<Setting<string>> = {}): Setting<string> {
  return {
    session: null,
    inherited: null,
    inherited_level: null,
    value: null,
    level: null,
    ...overrides,
  };
}

function toolSetting(overrides: Partial<Setting<boolean>> = {}): Setting<boolean> {
  return {
    session: null,
    inherited: true,
    inherited_level: "default",
    value: true,
    level: "default",
    ...overrides,
  };
}

/** A wire SessionConfiguration with all seven keys, each Setting with all five. */
function sessionConfiguration(overrides: Partial<SessionConfiguration> = {}): SessionConfiguration {
  return {
    model: { server_id: SERVER_A, model_name: "llama-3" },
    system_prompt: textSetting({
      inherited: "Stay in character.",
      inherited_level: "character",
      value: "Stay in character.",
      level: "character",
    }),
    tool_memo_search: toolSetting(),
    tool_session_search: toolSetting({
      inherited: false,
      inherited_level: "character",
      value: false,
      level: "character",
    }),
    tool_web_search: toolSetting({ session: false, value: false, level: "session" }),
    rp_language: textSetting({
      inherited: "English",
      inherited_level: "user",
      value: "English",
      level: "user",
    }),
    preferred_language: textSetting({
      session: "Russian",
      inherited: "German",
      inherited_level: "user",
      value: "Russian",
      level: "session",
    }),
    ...overrides,
  };
}

// ---------------------------------------------------------------- helpers

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

function serve(body: unknown, status = 200) {
  return stubFetch(() => Promise.resolve(jsonResponse(body, status)));
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Seen = { method: string; path: string; search: string };

function seen(mock: ReturnType<typeof stubFetch>): Seen[] {
  return mock.mock.calls.map(([input, init]) => {
    const url = requestUrl(input);
    return { method: requestMethod(input, init), path: url.pathname, search: url.search };
  });
}

/** The raw body string of the n-th request, or undefined when none was sent. */
function rawBody(mock: ReturnType<typeof stubFetch>, index = 0): string | undefined {
  const raw = mock.mock.calls[index]?.[1]?.body;
  if (raw === undefined || raw === null) return undefined;
  return typeof raw === "string" ? raw : String(raw);
}

/** The parsed JSON body of the n-th request, or undefined when none was sent. */
function sentBody(mock: ReturnType<typeof stubFetch>, index = 0): unknown {
  const raw = rawBody(mock, index);
  return raw === undefined ? undefined : (JSON.parse(raw) as unknown);
}

function bodyKeys(mock: ReturnType<typeof stubFetch>, index = 0): string[] {
  const body = sentBody(mock, index);
  return body === undefined ? [] : Object.keys(body as object).sort();
}

/** The rejection of a call that must not resolve. */
async function rejection(call: () => Promise<unknown>): Promise<unknown> {
  return call().then(
    () => {
      throw new Error("the call resolved, but it should have rejected");
    },
    (reason: unknown) => reason,
  );
}

/** Behaves like the platform fetch: rejects with the signal's reason once it aborts. */
function abortableFetch(): FetchFn {
  return (_input, init) =>
    new Promise<Response>((_resolve, reject) => {
      const signal = init?.signal;
      if (!signal) return; // never settles without a signal
      if (signal.aborted) {
        reject(signal.reason);
        return;
      }
      signal.addEventListener("abort", () => reject(signal.reason), { once: true });
    });
}

// ---------------------------------------------------------------------------
describe("fetchEnabledModels", () => {
  it("requests exactly GET /api/models — DoD-1", async () => {
    const mock = serve({ models: [] });
    await fetchEnabledModels();
    expect(seen(mock)).toEqual([{ method: "GET", path: "/api/models", search: "" }]);
  });

  it("resolves to the served models list, unwrapped and in served order — DoD-1", async () => {
    // Served order deliberately not sorted by any field: server B before server A,
    // and model names out of alphabetical order.
    const served = [
      enabledModel(SERVER_B, "Second box", "qwen-2"),
      enabledModel(SERVER_A, "First box", "zephyr"),
      enabledModel(SERVER_A, "First box", "llama-3"),
    ];
    serve({ models: served });
    await expect(fetchEnabledModels()).resolves.toEqual(served);
  });

  it("keeps every server_id the identical string the payload carried — DoD-1", async () => {
    serve({
      models: [
        enabledModel(SERVER_B, "Second box", "qwen-2"),
        enabledModel(SERVER_A, "First box", "llama-3"),
      ],
    });
    const got = await fetchEnabledModels();
    expect(got.map((model) => model.server_id)).toEqual(["7250000000000000302", "7250000000000000301"]);
    expect(typeof got[0].server_id).toBe("string");
    expect(typeof got[1].server_id).toBe("string");
  });

  it("resolves to an empty array when no model is enabled — DoD-1", async () => {
    serve({ models: [] });
    await expect(fetchEnabledModels()).resolves.toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("user settings", () => {
  const settings: UserSettings = { rp_language: "Japanese", preferred_language: "English" };

  it("fetchUserSettings requests exactly GET /api/me/settings and resolves to the served settings — DoD-2", async () => {
    const mock = serve(settings);
    await expect(fetchUserSettings()).resolves.toEqual(settings);
    expect(seen(mock)).toEqual([{ method: "GET", path: "/api/me/settings", search: "" }]);
  });

  it("fetchUserSettings resolves null languages as null — DoD-2", async () => {
    serve({ rp_language: null, preferred_language: null });
    await expect(fetchUserSettings()).resolves.toEqual({ rp_language: null, preferred_language: null });
  });

  it("updateUserSettings({ rp_language }) PATCHes /api/me/settings with exactly {\"rp_language\":\"Japanese\"} — DoD-2", async () => {
    const mock = serve(settings);
    await expect(updateUserSettings({ rp_language: "Japanese" })).resolves.toEqual(settings);
    expect(seen(mock)).toEqual([{ method: "PATCH", path: "/api/me/settings", search: "" }]);
    expect(sentBody(mock)).toStrictEqual({ rp_language: "Japanese" });
    expect(bodyKeys(mock)).toEqual(["rp_language"]);
    expect(rawBody(mock)).toBe('{"rp_language":"Japanese"}');
  });

  it("updateUserSettings({ preferred_language: null }) sends exactly {\"preferred_language\":null} — DoD-2", async () => {
    const served: UserSettings = { rp_language: "Japanese", preferred_language: null };
    const mock = serve(served);
    await expect(updateUserSettings({ preferred_language: null })).resolves.toEqual(served);
    expect(seen(mock)).toEqual([{ method: "PATCH", path: "/api/me/settings", search: "" }]);
    expect(sentBody(mock)).toStrictEqual({ preferred_language: null });
    expect(bodyKeys(mock)).toEqual(["preferred_language"]);
    expect(rawBody(mock)).toBe('{"preferred_language":null}');
  });
});

// ---------------------------------------------------------------------------
describe("fetchSessionConfiguration", () => {
  it("requests exactly GET /api/sessions/7250000000000000101/configuration — DoD-3", async () => {
    const mock = serve(sessionConfiguration());
    await fetchSessionConfiguration("7250000000000000101");
    expect(seen(mock)).toEqual([
      { method: "GET", path: "/api/sessions/7250000000000000101/configuration", search: "" },
    ]);
  });

  it("resolves to the served object unchanged — seven keys, every setting five keys — DoD-3", async () => {
    const served = sessionConfiguration();
    serve(served);
    const got = await fetchSessionConfiguration(SESSION_ID);
    expect(got).toStrictEqual(served);
    expect(Object.keys(got).sort()).toEqual([
      "model",
      "preferred_language",
      "rp_language",
      "system_prompt",
      "tool_memo_search",
      "tool_session_search",
      "tool_web_search",
    ]);
    for (const key of [
      "system_prompt",
      "tool_memo_search",
      "tool_session_search",
      "tool_web_search",
      "rp_language",
      "preferred_language",
    ] as const) {
      expect(Object.keys(got[key]).sort()).toEqual(["inherited", "inherited_level", "level", "session", "value"]);
    }
    expect(got.model?.server_id).toBe("7250000000000000301");
    expect(typeof got.model?.server_id).toBe("string");
  });

  it("resolves a null captured model as null — DoD-3", async () => {
    const served = sessionConfiguration({ model: null });
    serve(served);
    const got = await fetchSessionConfiguration(SESSION_ID);
    expect(got).toStrictEqual(served);
    expect(got.model).toBeNull();
  });

  it("addresses the session id verbatim — DoD-3", async () => {
    const mock = serve(sessionConfiguration());
    await fetchSessionConfiguration(OTHER_SESSION_ID);
    expect(seen(mock)[0].path).toBe(`/api/sessions/${OTHER_SESSION_ID}/configuration`);
  });
});

// ---------------------------------------------------------------------------
describe("updateSessionConfiguration", () => {
  it("a model patch PATCHes /api/sessions/<id>/configuration with exactly that one key — DoD-4", async () => {
    const served = sessionConfiguration({ model: { server_id: "7250000000000000301", model_name: "llama-3" } });
    const mock = serve(served);
    await expect(
      updateSessionConfiguration(SESSION_ID, {
        model: { server_id: "7250000000000000301", model_name: "llama-3" },
      }),
    ).resolves.toStrictEqual(served);
    expect(seen(mock)).toEqual([{ method: "PATCH", path: SESSION_CONFIG_PATH, search: "" }]);
    expect(sentBody(mock)).toStrictEqual({
      model: { server_id: "7250000000000000301", model_name: "llama-3" },
    });
    expect(bodyKeys(mock)).toEqual(["model"]);
    expect(typeof (sentBody(mock) as { model: { server_id: unknown } }).model.server_id).toBe("string");
  });

  it("{ system_prompt: null, tool_web_search: false } sends exactly those two keys with null preserved — DoD-4", async () => {
    const served = sessionConfiguration({
      tool_web_search: toolSetting({ session: false, value: false, level: "session" }),
    });
    const mock = serve(served);
    await expect(
      updateSessionConfiguration(SESSION_ID, { system_prompt: null, tool_web_search: false }),
    ).resolves.toStrictEqual(served);
    expect(seen(mock)).toEqual([{ method: "PATCH", path: SESSION_CONFIG_PATH, search: "" }]);
    expect(sentBody(mock)).toStrictEqual({ system_prompt: null, tool_web_search: false });
    expect(bodyKeys(mock)).toEqual(["system_prompt", "tool_web_search"]);
    const body = sentBody(mock) as Record<string, unknown>;
    expect(body.system_prompt).toBeNull();
    expect(body.tool_web_search).toBe(false);
  });

  it("addresses the session id verbatim — DoD-4", async () => {
    const mock = serve(sessionConfiguration());
    await updateSessionConfiguration(OTHER_SESSION_ID, { rp_language: "Japanese" });
    expect(seen(mock)).toEqual([
      { method: "PATCH", path: `/api/sessions/${OTHER_SESSION_ID}/configuration`, search: "" },
    ]);
    expect(sentBody(mock)).toStrictEqual({ rp_language: "Japanese" });
  });
});

// ---------------------------------------------------------------------------
describe("failures and aborts", () => {
  it("a 409 model_not_enabled envelope on the session PATCH rejects with an ApiError carrying code and detail.level session — DoD-5", async () => {
    serve(
      {
        error: {
          code: "model_not_enabled",
          message: "That model is not enabled.",
          detail: { server_id: SERVER_A, model_name: "llama-3", level: "session" },
        },
      },
      409,
    );
    const error = await rejection(() =>
      updateSessionConfiguration(SESSION_ID, { model: { server_id: SERVER_A, model_name: "llama-3" } }),
    );
    expect(isApiError(error)).toBe(true);
    if (!isApiError(error)) return;
    expect(error.code).toBe("model_not_enabled");
    expect(error.status).toBe(409);
    expect((error.detail as Record<string, unknown>).level).toBe("session");
    expect((error.detail as Record<string, unknown>).server_id).toBe(SERVER_A);
  });

  it("a 404 session_not_found envelope rejects fetchSessionConfiguration with an ApiError of that code — DoD-5", async () => {
    serve({ error: { code: "session_not_found", message: "No such session.", detail: {} } }, 404);
    const error = await rejection(() => fetchSessionConfiguration(SESSION_ID));
    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.code : null).toBe("session_not_found");
    expect(isApiError(error) ? error.status : null).toBe(404);
  });

  it("an abort during the session PATCH rejects with the abort, not an ApiError — DoD-5", async () => {
    const mock = stubFetch(abortableFetch());
    const controller = new AbortController();
    const pending = rejection(() =>
      updateSessionConfiguration(SESSION_ID, { tool_web_search: false }, controller.signal),
    );
    await vi.waitFor(() => expect(mock).toHaveBeenCalled());
    controller.abort();
    const caught = await pending;
    expect(isApiError(caught)).toBe(false);
    expect(caught).toBe(controller.signal.reason);
    expect((caught as { name?: unknown }).name).toBe("AbortError");
  });

  it("an already-aborted signal rejects fetchSessionConfiguration with the abort, not an ApiError — DoD-5", async () => {
    stubFetch(abortableFetch());
    const controller = new AbortController();
    controller.abort();
    const caught = await rejection(() => fetchSessionConfiguration(SESSION_ID, controller.signal));
    expect(isApiError(caught)).toBe(false);
    expect((caught as { name?: unknown }).name).toBe("AbortError");
  });

  it("an abort during fetchEnabledModels rejects with the abort, not an ApiError — DoD-5", async () => {
    const mock = stubFetch(abortableFetch());
    const controller = new AbortController();
    const pending = rejection(() => fetchEnabledModels(controller.signal));
    await vi.waitFor(() => expect(mock).toHaveBeenCalled());
    controller.abort();
    const caught = await pending;
    expect(isApiError(caught)).toBe(false);
    expect((caught as { name?: unknown }).name).toBe("AbortError");
  });
});

// ---------------------------------------------------------------------------
describe("no character-configuration call (D20)", () => {
  it("exports no character-configuration call — DoD-6", () => {
    const exported = Object.keys(configurationApi);
    expect(exported.filter((name) => /character/i.test(name))).toEqual([]);
  });

  it("no exported function requests a /api/characters path — DoD-6", async () => {
    // Every runtime export is one of the five calls; none reaches the character routes.
    const mock = stubFetch(() => Promise.resolve(jsonResponse(sessionConfiguration(), 200)));
    await fetchEnabledModels().catch(() => undefined);
    await fetchUserSettings().catch(() => undefined);
    await updateUserSettings({ rp_language: "Japanese" }).catch(() => undefined);
    await fetchSessionConfiguration(SESSION_ID).catch(() => undefined);
    await updateSessionConfiguration(SESSION_ID, { tool_memo_search: true }).catch(() => undefined);
    expect(seen(mock).filter((call) => call.path.startsWith("/api/characters"))).toEqual([]);
    const functions = Object.entries(configurationApi)
      .filter(([, value]) => typeof value === "function")
      .map(([name]) => name)
      .sort();
    expect(functions).toEqual([
      "fetchEnabledModels",
      "fetchSessionConfiguration",
      "fetchUserSettings",
      "updateSessionConfiguration",
      "updateUserSettings",
    ]);
  });
});
