// Feature 017, step 009 — the session configuration draft (DoD-1..DoD-7).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 009.context.md ("Comparing against `original`") and context.md: the Wire contract
// (`PATCH /api/sessions/{id}/configuration`, `Setting<T>`), D6 (verbatim prompt, trimmed
// languages), D18 (fresh draft, Inherit choices, only changed keys, no `model`), D19 (no
// notification) and the UI strings table:
//   - client errors: "Enter a system prompt, or choose Inherit." /
//     "Enter a language, or choose Inherit.";
//   - save failure: "Could not save the session configuration."
// Step 009 froze no setters: draft fields are assigned directly inside runInAction.
// Requests are stubbed and recorded by exact method + pathname + query.
import { runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelRef, SessionConfiguration, Setting } from "../../src/app/configurationApi";
import {
  SessionConfigDraft,
  canSubmit,
  clientErrors,
  errors,
  patchOf,
  submitSessionConfig,
} from "../../src/app/sessionConfigDraft";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown; raw: string | undefined };
type Handler = (request: Seen) => Response | Promise<Response>;

// ---------------------------------------------------------------- the spec's names
const SESSION_ID = "7250000000000000101";
const CONFIG_PATH = `/api/sessions/${SESSION_ID}/configuration`;

const PROMPT_REQUIRED = "Enter a system prompt, or choose Inherit.";
const LANGUAGE_REQUIRED = "Enter a language, or choose Inherit.";
const SAVE_FAILED = "Could not save the session configuration.";

// ---------------------------------------------------------------- payload builders
const CAPTURED: ModelRef = { server_id: "7250000000000000301", model_name: "alpha-13b" };

function promptSetting(session: string | null, inherited: string | null): Setting<string> {
  return {
    session,
    inherited,
    inherited_level: inherited === null ? null : "character",
    value: session ?? inherited,
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

/** DoD-1's configuration: the session overrides the system prompt ("S") and web search (off);
 * everything else is inherited (character prompt "C", user RP language "Japanese", no
 * preferred language anywhere). */
function dod1Configuration(): SessionConfiguration {
  return {
    model: { ...CAPTURED },
    system_prompt: promptSetting("S", "C"),
    tool_memo_search: toolSetting(null),
    tool_session_search: toolSetting(null),
    tool_web_search: toolSetting(false),
    rp_language: languageSetting(null, "Japanese"),
    preferred_language: languageSetting(null, null),
  };
}

/** What the server answers after a save: visibly different from DoD-1's configuration. */
function servedConfiguration(): SessionConfiguration {
  return {
    model: { ...CAPTURED },
    system_prompt: promptSetting(null, "C"),
    tool_memo_search: toolSetting(false),
    tool_session_search: toolSetting(null),
    tool_web_search: toolSetting(false),
    rp_language: languageSetting("French", "Japanese"),
    preferred_language: languageSetting(null, null),
  };
}

function freshDraft(config: SessionConfiguration = dod1Configuration()): SessionConfigDraft {
  return new SessionConfigDraft(SESSION_ID, config);
}

function edit(draft: SessionConfigDraft, change: (d: SessionConfigDraft) => void): void {
  runInAction(() => change(draft));
}

/** Drops keys whose value is `undefined`, so a `Partial<Record>` compares by its set keys. */
function defined(record: object): Record<string, unknown> {
  return Object.fromEntries(Object.entries(record).filter(([, value]) => value !== undefined));
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

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number, detail: unknown = {}): Response {
  return jsonResponse({ error: { code, message: "kv-19 backend prose.", detail } }, status);
}

function stubBackend(handler: Handler) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const url = requestUrl(input);
    const raw = rawBody(init);
    const request: Seen = {
      method: requestMethod(input, init),
      path: url.pathname,
      search: url.search,
      body: raw === undefined ? undefined : (JSON.parse(raw) as unknown),
      raw,
    };
    calls.push(request);
    return handler(request);
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

/** Answers only `PATCH <CONFIG_PATH>` (no query); anything else is a 500 and still recorded. */
function stubPatch(answer: () => Response | Promise<Response>) {
  return stubBackend((request) => {
    if (request.method === "PATCH" && request.path === CONFIG_PATH && request.search === "") {
      return answer();
    }
    return envelope("unexpected_request", 500);
  });
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

// ===========================================================================
describe("seeding a SessionConfigDraft", () => {
  it('starts the system prompt on "set" with the session text "S", not the inherited "C" — DoD-1', () => {
    const draft = freshDraft();

    expect(draft.systemPromptSource).toBe("set");
    expect(draft.systemPrompt).toBe("S");
  });

  it('starts web search "off" from the session override and the other two tools "inherit" — DoD-1', () => {
    const draft = freshDraft();

    expect(draft.toolWebSearch).toBe("off");
    expect(draft.toolMemoSearch).toBe("inherit");
    expect(draft.toolSessionSearch).toBe("inherit");
  });

  it('starts the RP language on "inherit" with the inherited text "Japanese" — DoD-1', () => {
    const draft = freshDraft();

    expect(draft.rpLanguageSource).toBe("inherit");
    expect(draft.rpLanguage).toBe("Japanese");
  });

  it('starts the preferred language on "inherit" with "" when nothing is inherited — DoD-1', () => {
    const draft = freshDraft();

    expect(draft.preferredLanguageSource).toBe("inherit");
    expect(draft.preferredLanguage).toBe("");
  });

  it('starts a tool "on" when its session override is true — DoD-1', () => {
    const config = dod1Configuration();
    config.tool_memo_search = toolSetting(true);

    const draft = freshDraft(config);

    expect(draft.toolMemoSearch).toBe("on");
  });

  it('starts a language on "set" with the session text when the session overrides it — DoD-1', () => {
    const config = dod1Configuration();
    config.rp_language = languageSetting("French", "Japanese");

    const draft = freshDraft(config);

    expect(draft.rpLanguageSource).toBe("set");
    expect(draft.rpLanguage).toBe("French");
  });

  it("keeps the session id and the loaded configuration as original, idle, with no errors — DoD-1", () => {
    const config = dod1Configuration();

    const draft = new SessionConfigDraft(SESSION_ID, config);

    expect(draft.sessionId).toBe(SESSION_ID);
    expect(draft.original).toEqual(dod1Configuration());
    expect(draft.submitStatus).toBe("idle");
    expect(defined(errors(draft))).toEqual({});
    expect(canSubmit(draft)).toBe(true);
  });
});

// ===========================================================================
describe("patchOf — only the overrides that changed", () => {
  it("is empty on an untouched draft — DoD-2", () => {
    expect(patchOf(freshDraft())).toEqual({});
  });

  it('is exactly { system_prompt: null } after switching the system prompt to "inherit" — DoD-2', () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.systemPromptSource = "inherit";
    });

    expect(patchOf(draft)).toEqual({ system_prompt: null });
  });

  it('is exactly { tool_memo_search: false } after setting memo search to "off" — DoD-2', () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.toolMemoSearch = "off";
    });

    expect(patchOf(draft)).toEqual({ tool_memo_search: false });
  });

  it('is exactly { tool_session_search: true } after setting session search to "on" — DoD-2', () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.toolSessionSearch = "on";
    });

    expect(patchOf(draft)).toEqual({ tool_session_search: true });
  });

  it('is exactly { tool_web_search: null } after setting web search from "off" to "inherit" — DoD-2', () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.toolWebSearch = "inherit";
    });

    expect(patchOf(draft)).toEqual({ tool_web_search: null });
  });

  it("is empty again when a changed choice is set back to the original — DoD-2", () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.toolWebSearch = "on";
      d.systemPromptSource = "inherit";
    });
    edit(draft, (d) => {
      d.toolWebSearch = "off";
      d.systemPromptSource = "set";
    });

    expect(patchOf(draft)).toEqual({});
  });

  it("never carries a model key, whatever else changed — DoD-2", () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.systemPromptSource = "inherit";
      d.toolMemoSearch = "off";
      d.toolSessionSearch = "on";
      d.toolWebSearch = "inherit";
      d.rpLanguageSource = "set";
      d.rpLanguage = "French";
      d.preferredLanguageSource = "set";
      d.preferredLanguage = "English";
    });

    const patch = patchOf(draft);

    expect(Object.keys(patch)).not.toContain("model");
    expect(patch).toEqual({
      system_prompt: null,
      tool_memo_search: false,
      tool_session_search: true,
      tool_web_search: null,
      rp_language: "French",
      preferred_language: "English",
    });
  });
});

// ===========================================================================
describe("patchOf — text normalisation", () => {
  it('sends a "set" RP language trimmed: "  French " gives { rp_language: "French" } — DoD-3', () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.rpLanguageSource = "set";
      d.rpLanguage = "  French ";
    });

    expect(patchOf(draft)).toEqual({ rp_language: "French" });
  });

  it('sends a "set" preferred language trimmed — DoD-3', () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.preferredLanguageSource = "set";
      d.preferredLanguage = "\tEnglish  ";
    });

    expect(patchOf(draft)).toEqual({ preferred_language: "English" });
  });

  it('sends a system prompt set to "  Be terse.\\n" with those exact characters — DoD-3', () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.systemPrompt = "  Be terse.\n";
    });

    const patch = patchOf(draft);

    expect(patch).toEqual({ system_prompt: "  Be terse.\n" });
    expect(patch.system_prompt).toBe("  Be terse.\n");
  });

  it("leaves a language out when its trimmed text equals the original session override — DoD-3", () => {
    const config = dod1Configuration();
    config.rp_language = languageSetting("French", "Japanese");
    const draft = freshDraft(config);
    edit(draft, (d) => {
      d.rpLanguage = "  French  ";
    });

    expect(patchOf(draft)).toEqual({});
  });

  it('ignores a text on "inherit" whatever it holds — DoD-3', () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.rpLanguage = "German";
      d.preferredLanguage = "   ";
    });

    expect(patchOf(draft)).toEqual({});
  });

  it('sends only null for a system prompt switched to "inherit" with edited text — DoD-3', () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.systemPrompt = "Something else entirely.";
      d.systemPromptSource = "inherit";
    });

    expect(patchOf(draft)).toEqual({ system_prompt: null });
  });

  it('gives no client error for a blank text on "inherit" — DoD-3', () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.preferredLanguage = "";
      d.rpLanguage = "  ";
    });

    expect(defined(clientErrors(draft))).toEqual({});
    expect(canSubmit(draft)).toBe(true);
  });
});

// ===========================================================================
describe("client errors", () => {
  it('gives the system prompt its error on "set" with blank text, and canSubmit is false — DoD-4', () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.systemPrompt = "";
    });

    expect(defined(clientErrors(draft))).toEqual({ systemPrompt: PROMPT_REQUIRED });
    expect(errors(draft).systemPrompt).toBe(PROMPT_REQUIRED);
    expect(canSubmit(draft)).toBe(false);
  });

  it("treats a whitespace-only system prompt as blank — DoD-4", () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.systemPrompt = "  \n\t ";
    });

    expect(defined(clientErrors(draft))).toEqual({ systemPrompt: PROMPT_REQUIRED });
    expect(canSubmit(draft)).toBe(false);
  });

  it('gives the RP language its error on "set" with blank text — DoD-4', () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.rpLanguageSource = "set";
      d.rpLanguage = "   ";
    });

    expect(defined(clientErrors(draft))).toEqual({ rpLanguage: LANGUAGE_REQUIRED });
    expect(errors(draft).rpLanguage).toBe(LANGUAGE_REQUIRED);
    expect(canSubmit(draft)).toBe(false);
  });

  it('gives the preferred language its error on "set" with blank text — DoD-4', () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.preferredLanguageSource = "set";
      d.preferredLanguage = "";
    });

    expect(defined(clientErrors(draft))).toEqual({ preferredLanguage: LANGUAGE_REQUIRED });
    expect(errors(draft).preferredLanguage).toBe(LANGUAGE_REQUIRED);
    expect(canSubmit(draft)).toBe(false);
  });

  it("keys each blank setting's error by its own field — DoD-4", () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.systemPrompt = "";
      d.rpLanguageSource = "set";
      d.rpLanguage = "";
      d.preferredLanguageSource = "set";
      d.preferredLanguage = " ";
    });

    expect(defined(clientErrors(draft))).toEqual({
      systemPrompt: PROMPT_REQUIRED,
      rpLanguage: LANGUAGE_REQUIRED,
      preferredLanguage: LANGUAGE_REQUIRED,
    });
  });

  it('removes the error when the setting is switched to "inherit", and canSubmit is true again — DoD-4', () => {
    const draft = freshDraft();
    edit(draft, (d) => {
      d.systemPrompt = "";
      d.rpLanguageSource = "set";
      d.rpLanguage = "";
    });
    expect(canSubmit(draft)).toBe(false);

    edit(draft, (d) => {
      d.systemPromptSource = "inherit";
      d.rpLanguageSource = "inherit";
    });

    expect(defined(clientErrors(draft))).toEqual({});
    expect(errors(draft).systemPrompt).toBeUndefined();
    expect(errors(draft).rpLanguage).toBeUndefined();
    expect(canSubmit(draft)).toBe(true);
  });

  it("makes submitSessionConfig do nothing while a client error stands — DoD-4", async () => {
    const backend = stubPatch(() => jsonResponse(servedConfiguration(), 200));
    const onSaved = vi.fn();
    const draft = freshDraft();
    edit(draft, (d) => {
      d.toolMemoSearch = "off";
      d.systemPrompt = "";
    });

    await submitSessionConfig(draft, onSaved);
    await flush();

    expect(backend.calls).toEqual([]);
    expect(onSaved).not.toHaveBeenCalled();
    expect(draft.submitStatus).toBe("idle");
  });
});

// ===========================================================================
describe("submitSessionConfig — a non-empty patch", () => {
  it("sends PATCH /api/sessions/<id>/configuration with exactly patchOf's keys and no model — DoD-5", async () => {
    const backend = stubPatch(() => jsonResponse(servedConfiguration(), 200));
    const draft = freshDraft();
    edit(draft, (d) => {
      d.systemPromptSource = "inherit";
      d.toolMemoSearch = "off";
      d.rpLanguageSource = "set";
      d.rpLanguage = "  French ";
    });

    await submitSessionConfig(draft, vi.fn());

    expect(backend.calls).toHaveLength(1);
    const [call] = backend.calls;
    expect(call.method).toBe("PATCH");
    expect(call.path).toBe(CONFIG_PATH);
    expect(call.search).toBe("");
    expect(call.body).toEqual({ system_prompt: null, tool_memo_search: false, rp_language: "French" });
    expect(Object.keys(call.body as object).sort()).toEqual(
      ["rp_language", "system_prompt", "tool_memo_search"],
    );
    expect(Object.keys(call.body as object)).not.toContain("model");
  });

  it('sends a verbatim system prompt and is "done" with onSaved given the served configuration on 200 — DoD-5', async () => {
    const served = servedConfiguration();
    const backend = stubPatch(() => jsonResponse(served, 200));
    const onSaved = vi.fn<(saved: SessionConfiguration) => void>();
    const draft = freshDraft();
    edit(draft, (d) => {
      d.systemPrompt = "  Be terse.\n";
    });

    await submitSessionConfig(draft, onSaved);

    expect(backend.calls).toHaveLength(1);
    expect(backend.calls[0].body).toEqual({ system_prompt: "  Be terse.\n" });
    expect(draft.submitStatus).toBe("done");
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onSaved.mock.calls[0][0]).toEqual(servedConfiguration());
  });

  it('is "submitting" with canSubmit false while the PATCH is in flight — DoD-5', async () => {
    const answer = deferred<Response>();
    stubPatch(() => answer.promise);
    const onSaved = vi.fn();
    const draft = freshDraft();
    edit(draft, (d) => {
      d.toolWebSearch = "inherit";
    });

    const pending = submitSessionConfig(draft, onSaved);
    await flush();

    expect(draft.submitStatus).toBe("submitting");
    expect(canSubmit(draft)).toBe(false);
    expect(onSaved).not.toHaveBeenCalled();

    answer.resolve(jsonResponse(servedConfiguration(), 200));
    await pending;

    expect(draft.submitStatus).toBe("done");
    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  it("sends nothing more when submitted again while a PATCH is in flight — DoD-5", async () => {
    const answer = deferred<Response>();
    const backend = stubPatch(() => answer.promise);
    const draft = freshDraft();
    edit(draft, (d) => {
      d.toolWebSearch = "inherit";
    });

    const first = submitSessionConfig(draft, vi.fn());
    await flush();
    await submitSessionConfig(draft, vi.fn());

    expect(backend.calls).toHaveLength(1);

    answer.resolve(jsonResponse(servedConfiguration(), 200));
    await first;
  });
});

// ===========================================================================
describe("submitSessionConfig — an empty patch", () => {
  it("makes no request and calls onSaved with the original configuration — DoD-6", async () => {
    const backend = stubPatch(() => jsonResponse(servedConfiguration(), 200));
    const onSaved = vi.fn<(saved: SessionConfiguration) => void>();
    const draft = freshDraft();

    await submitSessionConfig(draft, onSaved);
    await flush();

    expect(backend.mock).not.toHaveBeenCalled();
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onSaved.mock.calls[0][0]).toEqual(dod1Configuration());
  });

  it("makes no request when an inherit text was edited but no override changed — DoD-6", async () => {
    const backend = stubPatch(() => jsonResponse(servedConfiguration(), 200));
    const onSaved = vi.fn<(saved: SessionConfiguration) => void>();
    const draft = freshDraft();
    edit(draft, (d) => {
      d.rpLanguage = "German";
      d.toolMemoSearch = "off";
    });
    edit(draft, (d) => {
      d.toolMemoSearch = "inherit";
    });

    await submitSessionConfig(draft, onSaved);
    await flush();

    expect(backend.mock).not.toHaveBeenCalled();
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onSaved.mock.calls[0][0]).toEqual(dod1Configuration());
  });
});

// ===========================================================================
const FAILURES: [label: string, answer: () => Response][] = [
  ["a 500", () => envelope("internal_error", 500)],
  [
    "a 422",
    () =>
      jsonResponse(
        { detail: [{ loc: ["body", "rp_language"], msg: "kv-19 field prose.", type: "value_error" }] },
        422,
      ),
  ],
  ["a 422 envelope", () => envelope("validation_error", 422, { field: "rp_language" })],
  ["a 409 model_not_enabled", () => envelope("model_not_enabled", 409, { level: "session" })],
  [
    "a transport failure",
    () => {
      throw new TypeError("Failed to fetch");
    },
  ],
];

describe("submitSessionConfig — a failed PATCH", () => {
  it.each(FAILURES)(
    'on %s sets only the general error, returns to "idle", keeps every field, skips onSaved — DoD-7',
    async (_label, answer) => {
      stubPatch(answer);
      const onSaved = vi.fn();
      const draft = freshDraft();
      edit(draft, (d) => {
        d.systemPromptSource = "inherit";
        d.systemPrompt = "  Be terse.\n";
        d.toolMemoSearch = "off";
        d.toolSessionSearch = "on";
        d.toolWebSearch = "inherit";
        d.rpLanguageSource = "set";
        d.rpLanguage = "  French ";
        d.preferredLanguageSource = "set";
        d.preferredLanguage = "English";
      });

      await expect(submitSessionConfig(draft, onSaved)).resolves.toBeUndefined();

      expect(defined(draft.serverErrors)).toEqual({ general: SAVE_FAILED });
      expect(errors(draft).general).toBe(SAVE_FAILED);
      expect(errors(draft).rpLanguage).toBeUndefined();
      expect(draft.submitStatus).toBe("idle");
      expect(onSaved).not.toHaveBeenCalled();
      expect({
        systemPromptSource: draft.systemPromptSource,
        systemPrompt: draft.systemPrompt,
        toolMemoSearch: draft.toolMemoSearch,
        toolSessionSearch: draft.toolSessionSearch,
        toolWebSearch: draft.toolWebSearch,
        rpLanguageSource: draft.rpLanguageSource,
        rpLanguage: draft.rpLanguage,
        preferredLanguageSource: draft.preferredLanguageSource,
        preferredLanguage: draft.preferredLanguage,
      }).toEqual({
        systemPromptSource: "inherit",
        systemPrompt: "  Be terse.\n",
        toolMemoSearch: "off",
        toolSessionSearch: "on",
        toolWebSearch: "inherit",
        rpLanguageSource: "set",
        rpLanguage: "  French ",
        preferredLanguageSource: "set",
        preferredLanguage: "English",
      });
      expect(notifyFailureSpy).not.toHaveBeenCalled();
    },
  );

  it("keeps original unchanged after a failure — DoD-7", async () => {
    stubPatch(() => envelope("internal_error", 500));
    const draft = freshDraft();
    edit(draft, (d) => {
      d.toolMemoSearch = "off";
    });

    await submitSessionConfig(draft, vi.fn());

    expect(draft.original).toEqual(dod1Configuration());
    expect(patchOf(draft)).toEqual({ tool_memo_search: false });
  });
});
