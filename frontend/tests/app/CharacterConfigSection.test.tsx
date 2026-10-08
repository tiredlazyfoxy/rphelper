// Feature 018, step 007 — the character page's configuration block (DoD-1..DoD-8).
// DoD-9 is [manual/live] and carries no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 007.context.md ("Mantine specifics", "Test-file notes") and context.md: D9, the UI strings
// table (Configuration block, Model control, System prompt control, Tool controls,
// resolved-value lines, load and save failures) and "Test conventions". Every expected
// sentence and label is a literal from the strings table, never computed by a derivation.
//
// Recognition conventions (for the verifier):
// - The block is the region named "Configuration"; everything is scoped inside it, except
//   Mantine `Select` options, which render in a portal and are read off `screen` by role
//   "option".
// - The model picker is the field labelled "Model" (a combobox, else a textbox, else by
//   label — the 017 SessionConfigBar.test.tsx precedent). Its shown value is the input value.
//   An option counts as disabled when it carries `aria-disabled="true"`, a `disabled`
//   attribute, or Mantine's `data-combobox-disabled` / `data-disabled` marker.
// - Each `SegmentedControl` is a radio group named by its label (else a group of that name);
//   its options are radios found inside that group, since "Default" / "On" / "Off" repeat.
// - Resolved-value lines are read from the region's whitespace-normalised text in document
//   order (one under each control, in the order the Interface intent lists the controls).
// - A notification is `.mantine-Notification-root`; `notifyFailure` is also mocked and spied.
// - Stubs key on the exact method + pathname + query (context.md "Test conventions").
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CharacterConfiguration, EnabledModel, ModelRef } from "../../src/app/configurationApi";
import { CharacterConfigSection } from "../../src/app/CharacterConfigSection";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };
type User = ReturnType<typeof userEvent.setup>;
type Answer = () => Response | Promise<Response>;

// ---------------------------------------------------------------- the spec's names
const REGION_NAME = "Configuration";
const MODEL_LABEL = "Model";
const PROMPT_LABEL = "Character system prompt";
const MEMO_SEARCH = "Memo search";
const SESSION_SEARCH = "Session search";
const WEB_SEARCH = "Web search";
const RP_LANGUAGE = "RP language";
const PREFERRED_LANGUAGE = "Preferred language";

const FIRST_ENABLED_MODEL = "First enabled model";
const MODEL_DESCRIPTION = "Applies to sessions started from now on. Existing sessions keep their model.";
const MODEL_NOT_SET = "Not set: new sessions take the first enabled model.";
const SET_HERE = "Set on this character.";
const PROMPT_NOT_SET = "Not set: no system prompt.";
const TOOL_DEFAULT = "On (default)";
const TOOL_ON_HERE = "On (set on this character)";
const TOOL_OFF_HERE = "Off (set on this character)";

const LOAD_FAILED = "Could not load the configuration";
const RETRY_NAME = "Retry";
const NO_LONGER_ENABLED = "That model is no longer enabled.";
const COULD_NOT_SAVE = "Could not save the configuration.";

const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- fixtures
const CHARACTER_ID = "7250000000000000001";
const CONFIG_PATH = `/api/characters/${CHARACTER_ID}/configuration`;
const MODELS_PATH = "/api/models";

const S1_ID = "7250000000000000301";
const S2_ID = "7250000000000000302";

const MODEL_A: EnabledModel = { server_id: S1_ID, server_name: "S1", model_name: "A" };
const MODEL_B: EnabledModel = { server_id: S2_ID, server_name: "S2", model_name: "B" };

const REF_A: ModelRef = { server_id: S1_ID, model_name: "A" };
const REF_B: ModelRef = { server_id: S2_ID, model_name: "B" };

const LABEL_A = "A (S1)";
const LABEL_B = "B (S2)";
const LABEL_A_NOT_ENABLED = "A (not enabled)";

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

/** DoD-1's configuration: model A on S1, prompt "Be terse.", memo null, session false, web true. */
function dod1Configuration(overrides: Partial<CharacterConfiguration> = {}): CharacterConfiguration {
  return configuration({
    model: { ...REF_A },
    system_prompt: "Be terse.",
    tool_memo_search: null,
    tool_session_search: false,
    tool_web_search: true,
    ...overrides,
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

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number, detail: unknown = {}): Response {
  return jsonResponse({ error: { code, message: "rq-58 backend prose.", detail } }, status);
}

function serverError(): Response {
  return envelope("internal_error", 500);
}

function modelsAnswer(models: EnabledModel[]): Response {
  return jsonResponse({ models: models.map((model) => ({ ...model })) }, 200);
}

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

type Routes = {
  config: Answer;
  models: Answer;
  patch?: Answer;
};

/**
 * Answers `GET <CONFIG_PATH>`, `GET /api/models` and `PATCH <CONFIG_PATH>` (no query) from the
 * mutable `routes`; anything else is a 500. Every request is recorded in order.
 */
function stubBackend(routes: Routes) {
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
    if (request.search === "") {
      if (request.method === "GET" && request.path === CONFIG_PATH) return routes.config();
      if (request.method === "GET" && request.path === MODELS_PATH) return routes.models();
      if (request.method === "PATCH" && request.path === CONFIG_PATH && routes.patch !== undefined) {
        return routes.patch();
      }
    }
    return serverError();
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls, routes };
}

function requestsFor(calls: Seen[], method: string, path: string): Seen[] {
  return calls.filter((call) => call.method === method && call.path === path);
}

function configGets(calls: Seen[]): Seen[] {
  return requestsFor(calls, "GET", CONFIG_PATH);
}

function modelsGets(calls: Seen[]): Seen[] {
  return requestsFor(calls, "GET", MODELS_PATH);
}

function configPatches(calls: Seen[]): Seen[] {
  return requestsFor(calls, "PATCH", CONFIG_PATH);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

function newUser(): User {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

function renderSection() {
  return render(
    <AppProviders>
      <CharacterConfigSection characterId={CHARACTER_ID} headingOrder={3} />
    </AppProviders>,
  );
}

// ---------------------------------------------------------------- queries
function region(): HTMLElement {
  return screen.getByRole("region", { name: REGION_NAME });
}

function regionText(): string {
  return (region().textContent ?? "").replace(/\s+/g, " ");
}

function modelSelect(): HTMLElement {
  const scope = within(region());
  return (
    scope.queryByRole("combobox", { name: MODEL_LABEL }) ??
    scope.queryByRole("textbox", { name: MODEL_LABEL }) ??
    scope.getByLabelText(MODEL_LABEL)
  );
}

function queryModelSelect(): HTMLElement | null {
  const scope = within(region());
  return (
    scope.queryByRole("combobox", { name: MODEL_LABEL }) ??
    scope.queryByRole("textbox", { name: MODEL_LABEL })
  );
}

/** What the "Model" picker currently displays. */
function shownModel(): string {
  const element = modelSelect();
  const shown = element instanceof HTMLInputElement ? element.value : element.textContent ?? "";
  return shown.trim();
}

function promptBox(): HTMLElement {
  return within(region()).getByRole("textbox", { name: PROMPT_LABEL });
}

function group(label: string): HTMLElement {
  const scope = within(region());
  return scope.queryByRole("radiogroup", { name: label }) ?? scope.getByRole("group", { name: label });
}

function radio(groupLabel: string, option: string): HTMLElement {
  return within(group(groupLabel)).getByRole("radio", { name: option });
}

function optionDisabled(option: HTMLElement): boolean {
  return (
    option.getAttribute("aria-disabled") === "true" ||
    option.hasAttribute("disabled") ||
    option.hasAttribute("data-combobox-disabled") ||
    option.hasAttribute("data-disabled")
  );
}

async function openPicker(user: User): Promise<void> {
  await user.click(modelSelect());
  await waitFor(() => {
    expect(screen.queryAllByRole("option").length).toBeGreaterThan(0);
  });
  await flush();
}

async function chooseOption(user: User, name: string): Promise<void> {
  await user.click(screen.getByRole("option", { name }));
  await flush();
}

async function chooseTool(user: User, groupLabel: string, option: string): Promise<void> {
  await user.click(radio(groupLabel, option));
  await flush();
}

/**
 * Every resolved-value line in the region, in document order. Adjacent elements may glue their
 * text together, so each alternative matches only the line's own words.
 */
function resolvedLines(): string[] {
  const pattern =
    /Not set: new sessions take the first enabled model\.|Not set: no system prompt\.|Set on this character\.|On \(default\)|On \(set on this character\)|Off \(set on this character\)/g;
  return regionText().match(pattern) ?? [];
}

function notificationsShown(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION));
}

async function renderReady(config: CharacterConfiguration, models: EnabledModel[], patch?: Answer) {
  const backend = stubBackend({
    config: () => jsonResponse(config, 200),
    models: () => modelsAnswer(models),
    patch,
  });
  renderSection();
  await flush();
  await waitFor(() => {
    expect(queryModelSelect()).not.toBeNull();
  });
  return backend;
}

// ===========================================================================
describe("the block over a loaded configuration (US-096.AC-1, UC-048, US-059.AC-2, US-061.AC-3)", () => {
  it('renders the region "Configuration" headed "Configuration" at the given heading order — DoD-1', async () => {
    await renderReady(dod1Configuration(), [MODEL_A, MODEL_B]);

    expect(within(region()).getByRole("heading", { name: REGION_NAME, level: 3 })).toBeInTheDocument();
  });

  it('shows "Model" on "A (S1)", the prompt "Be terse.", and each tool on its held value — DoD-1', async () => {
    const { calls } = await renderReady(dod1Configuration(), [MODEL_A, MODEL_B]);

    expect(shownModel()).toBe(LABEL_A);
    expect(promptBox()).toHaveValue("Be terse.");
    expect(radio(MEMO_SEARCH, "Default")).toBeChecked();
    expect(radio(SESSION_SEARCH, "Off")).toBeChecked();
    expect(radio(WEB_SEARCH, "On")).toBeChecked();

    // Each tool control offers exactly Default / On / Off.
    for (const label of [MEMO_SEARCH, SESSION_SEARCH, WEB_SEARCH]) {
      expect(within(group(label)).getAllByRole("radio")).toHaveLength(3);
      for (const option of ["Default", "On", "Off"]) {
        expect(radio(label, option)).toBeInTheDocument();
      }
    }

    // Exactly the load: one read of each, nothing written on render.
    expect(configGets(calls)).toHaveLength(1);
    expect(modelsGets(calls)).toHaveLength(1);
    expect(configPatches(calls)).toEqual([]);
  });

  it("shows the resolved-value line under each control — DoD-1", async () => {
    await renderReady(dod1Configuration(), [MODEL_A, MODEL_B]);

    expect(resolvedLines()).toEqual([SET_HERE, SET_HERE, TOOL_DEFAULT, TOOL_OFF_HERE, TOOL_ON_HERE]);
  });

  it('holds no "RP language" and no "Preferred language" control, and shows no notification — DoD-1', async () => {
    await renderReady(dod1Configuration(), [MODEL_A, MODEL_B]);

    const scope = within(region());
    for (const name of [RP_LANGUAGE, PREFERRED_LANGUAGE]) {
      for (const role of ["combobox", "textbox", "radiogroup", "group", "button"] as const) {
        expect(scope.queryByRole(role, { name })).toBeNull();
      }
      expect(scope.queryByLabelText(name)).toBeNull();
    }
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(notificationsShown()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
describe("the model description and the unset model (US-106.AC-1, US-139.AC-1)", () => {
  it('the "Model" control carries the description "Applies to sessions started from now on. Existing sessions keep their model." — DoD-2', async () => {
    await renderReady(dod1Configuration(), [MODEL_A, MODEL_B]);

    expect(within(region()).getByText(MODEL_DESCRIPTION)).toBeInTheDocument();
  });

  it('with model null the picker shows "First enabled model" and the line "Not set: new sessions take the first enabled model." — DoD-2', async () => {
    await renderReady(dod1Configuration({ model: null }), [MODEL_A, MODEL_B]);

    expect(shownModel()).toBe(FIRST_ENABLED_MODEL);
    expect(resolvedLines()[0]).toBe(MODEL_NOT_SET);
    expect(regionText()).toContain(MODEL_NOT_SET);
  });

  it('opening the picker lists "First enabled model" first, then "A (S1)", "B (S2)" — DoD-2', async () => {
    const user = newUser();
    await renderReady(dod1Configuration({ model: null }), [MODEL_A, MODEL_B]);

    await openPicker(user);
    const texts = screen.queryAllByRole("option").map((option) => (option.textContent ?? "").trim());
    expect(texts).toEqual([FIRST_ENABLED_MODEL, LABEL_A, LABEL_B]);
  });
});

// ===========================================================================
describe("choosing a model (US-059.AC-2, D9 — never optimistic)", () => {
  it('choosing "B (S2)" PATCHes exactly {"model":{…B…}}; pending: disabled and still "A (S1)"; after the 200: "B (S2)" — DoD-3', async () => {
    const user = newUser();
    const pending = deferred<Response>();
    const { calls } = await renderReady(dod1Configuration(), [MODEL_A, MODEL_B], () => pending.promise);
    expect(shownModel()).toBe(LABEL_A);

    await openPicker(user);
    await chooseOption(user, LABEL_B);

    const sent = configPatches(calls);
    expect(sent).toHaveLength(1);
    expect(sent[0].search).toBe("");
    expect(sent[0].body).toEqual({ model: { server_id: S2_ID, model_name: "B" } });

    await waitFor(() => {
      expect(modelSelect()).toBeDisabled();
    });
    expect(shownModel()).toBe(LABEL_A);

    await act(async () => {
      pending.resolve(jsonResponse(dod1Configuration({ model: { ...REF_B } }), 200));
    });
    await flush();

    expect(shownModel()).toBe(LABEL_B);
    expect(modelSelect()).toBeEnabled();
    expect(configPatches(calls)).toHaveLength(1);
  });

  it('choosing "First enabled model" PATCHes exactly {"model":null} — DoD-3', async () => {
    const user = newUser();
    const { calls } = await renderReady(dod1Configuration(), [MODEL_A, MODEL_B], () =>
      jsonResponse(dod1Configuration({ model: null }), 200),
    );

    await openPicker(user);
    await chooseOption(user, FIRST_ENABLED_MODEL);

    const sent = configPatches(calls);
    expect(sent).toHaveLength(1);
    expect(sent[0].search).toBe("");
    expect(sent[0].body).toEqual({ model: null });

    await waitFor(() => {
      expect(shownModel()).toBe(FIRST_ENABLED_MODEL);
    });
  });
});

// ===========================================================================
describe("a configured model that is not enabled (D9)", () => {
  it('shows "A (not enabled)"; opening the picker shows that option disabled; pressing it sends nothing — DoD-4', async () => {
    const user = newUser();
    const { calls } = await renderReady(dod1Configuration(), [MODEL_B], () =>
      jsonResponse(dod1Configuration(), 200),
    );

    expect(shownModel()).toBe(LABEL_A_NOT_ENABLED);

    await openPicker(user);
    const notEnabled = screen.getByRole("option", { name: LABEL_A_NOT_ENABLED });
    expect(optionDisabled(notEnabled)).toBe(true);
    expect(optionDisabled(screen.getByRole("option", { name: LABEL_B }))).toBe(false);

    await user.click(notEnabled);
    await flush();
    expect(configPatches(calls)).toEqual([]);
  });
});

// ===========================================================================
describe("the tool switches (US-062.AC-1, D9)", () => {
  it('"Off" on "Memo search" PATCHes exactly {"tool_memo_search":false}; after the 200 it shows Off with "Off (set on this character)" — DoD-5', async () => {
    const user = newUser();
    const { calls } = await renderReady(dod1Configuration(), [MODEL_A, MODEL_B], () =>
      jsonResponse(dod1Configuration({ tool_memo_search: false }), 200),
    );

    await chooseTool(user, MEMO_SEARCH, "Off");

    const sent = configPatches(calls);
    expect(sent).toHaveLength(1);
    expect(sent[0].search).toBe("");
    expect(sent[0].body).toEqual({ tool_memo_search: false });

    await waitFor(() => {
      expect(radio(MEMO_SEARCH, "Off")).toBeChecked();
    });
    expect(resolvedLines()).toEqual([SET_HERE, SET_HERE, TOOL_OFF_HERE, TOOL_OFF_HERE, TOOL_ON_HERE]);
  });

  it('"Default" on "Session search" PATCHes exactly {"tool_session_search":null}; after the 200 it shows Default with "On (default)" — DoD-5', async () => {
    const user = newUser();
    const { calls } = await renderReady(dod1Configuration(), [MODEL_A, MODEL_B], () =>
      jsonResponse(dod1Configuration({ tool_session_search: null }), 200),
    );

    await chooseTool(user, SESSION_SEARCH, "Default");

    const sent = configPatches(calls);
    expect(sent).toHaveLength(1);
    expect(sent[0].search).toBe("");
    expect(sent[0].body).toEqual({ tool_session_search: null });

    await waitFor(() => {
      expect(radio(SESSION_SEARCH, "Default")).toBeChecked();
    });
    expect(resolvedLines()).toEqual([SET_HERE, SET_HERE, TOOL_DEFAULT, TOOL_DEFAULT, TOOL_ON_HERE]);
  });

  it("the control and its line follow the served configuration, not the choice — DoD-5", async () => {
    const user = newUser();
    // Choosing memo "On" sends true; the server answers memo null and web search off, and the
    // block renders exactly what was served (never optimistic).
    const { calls } = await renderReady(dod1Configuration(), [MODEL_A, MODEL_B], () =>
      jsonResponse(dod1Configuration({ tool_memo_search: null, tool_web_search: false }), 200),
    );

    await chooseTool(user, MEMO_SEARCH, "On");

    expect(configPatches(calls)).toHaveLength(1);
    expect(configPatches(calls)[0].body).toEqual({ tool_memo_search: true });
    await waitFor(() => {
      expect(radio(WEB_SEARCH, "Off")).toBeChecked();
    });
    expect(radio(MEMO_SEARCH, "Default")).toBeChecked();
    expect(resolvedLines()).toEqual([SET_HERE, SET_HERE, TOOL_DEFAULT, TOOL_OFF_HERE, TOOL_OFF_HERE]);
  });
});

// ===========================================================================
describe("the character system prompt (017 D6, D9)", () => {
  it('typing "Stay in character." and blurring PATCHes exactly {"system_prompt":"Stay in character."} — DoD-6', async () => {
    const user = newUser();
    const { calls } = await renderReady(dod1Configuration({ system_prompt: null }), [MODEL_A, MODEL_B], () =>
      jsonResponse(dod1Configuration({ system_prompt: "Stay in character." }), 200),
    );

    const box = promptBox();
    await user.click(box);
    await user.type(box, "Stay in character.");
    expect(configPatches(calls)).toEqual([]);

    await user.tab();
    await flush();

    const sent = configPatches(calls);
    expect(sent).toHaveLength(1);
    expect(sent[0].search).toBe("");
    expect(sent[0].body).toEqual({ system_prompt: "Stay in character." });

    await waitFor(() => {
      expect(resolvedLines()[1]).toBe(SET_HERE);
    });
    expect(promptBox()).toHaveValue("Stay in character.");
  });

  it("blurring with no change sends nothing — DoD-6", async () => {
    const user = newUser();
    const { calls } = await renderReady(dod1Configuration(), [MODEL_A, MODEL_B], () =>
      jsonResponse(dod1Configuration(), 200),
    );

    await user.click(promptBox());
    await user.tab();
    await flush();

    expect(configPatches(calls)).toEqual([]);
  });

  it('clearing the prompt and blurring PATCHes exactly {"system_prompt":null}; the line then reads "Not set: no system prompt." — DoD-6', async () => {
    const user = newUser();
    const { calls } = await renderReady(dod1Configuration(), [MODEL_A, MODEL_B], () =>
      jsonResponse(dod1Configuration({ system_prompt: null }), 200),
    );
    expect(promptBox()).toHaveValue("Be terse.");

    await user.clear(promptBox());
    await user.tab();
    await flush();

    const sent = configPatches(calls);
    expect(sent).toHaveLength(1);
    expect(sent[0].search).toBe("");
    expect(sent[0].body).toEqual({ system_prompt: null });

    await waitFor(() => {
      expect(resolvedLines()[1]).toBe(PROMPT_NOT_SET);
    });
    expect(regionText()).toContain(PROMPT_NOT_SET);
  });
});

// ===========================================================================
describe("save failures render in the region (D9; 017 D19's posture)", () => {
  it('a 409 model_not_enabled on choosing a model shows "That model is no longer enabled.", keeps "A (S1)" and re-requests GET /api/models — DoD-7', async () => {
    const user = newUser();
    const { calls } = await renderReady(dod1Configuration(), [MODEL_A, MODEL_B], () =>
      envelope("model_not_enabled", 409, { server_id: S2_ID, model_name: "B", level: "character" }),
    );
    expect(modelsGets(calls)).toHaveLength(1);

    await openPicker(user);
    await chooseOption(user, LABEL_B);

    expect(configPatches(calls)).toHaveLength(1);
    await waitFor(() => {
      expect(regionText()).toContain(NO_LONGER_ENABLED);
    });
    expect(shownModel()).toBe(LABEL_A);
    await waitFor(() => {
      expect(modelsGets(calls)).toHaveLength(2);
    });
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(notificationsShown()).toEqual([]);
  });

  it('a 500 on a tool save shows "Could not save the configuration." and keeps the held value — DoD-7', async () => {
    const user = newUser();
    const { calls } = await renderReady(dod1Configuration(), [MODEL_A, MODEL_B], () => serverError());

    await chooseTool(user, WEB_SEARCH, "Off");

    expect(configPatches(calls)).toHaveLength(1);
    expect(configPatches(calls)[0].body).toEqual({ tool_web_search: false });
    await waitFor(() => {
      expect(regionText()).toContain(COULD_NOT_SAVE);
    });
    expect(radio(WEB_SEARCH, "On")).toBeChecked();
    expect(regionText()).not.toContain(NO_LONGER_ENABLED);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(notificationsShown()).toEqual([]);
  });
});

// ===========================================================================
describe("a failed load and Retry (D9)", () => {
  it('a failed configuration load shows "Could not load the configuration" and "Retry"; Retry re-requests both and the controls render — DoD-8', async () => {
    const user = newUser();
    const backend = stubBackend({
      config: () => serverError(),
      models: () => modelsAnswer([MODEL_A, MODEL_B]),
    });
    renderSection();
    await flush();

    await waitFor(() => {
      expect(regionText()).toContain(LOAD_FAILED);
    });
    const retry = within(region()).getByRole("button", { name: RETRY_NAME });
    expect(queryModelSelect()).toBeNull();
    expect(configGets(backend.calls)).toHaveLength(1);
    expect(modelsGets(backend.calls)).toHaveLength(1);

    backend.routes.config = () => jsonResponse(dod1Configuration(), 200);
    await user.click(retry);
    await flush();

    expect(configGets(backend.calls)).toHaveLength(2);
    expect(modelsGets(backend.calls)).toHaveLength(2);
    await waitFor(() => {
      expect(queryModelSelect()).not.toBeNull();
    });
    expect(shownModel()).toBe(LABEL_A);
    expect(promptBox()).toHaveValue("Be terse.");
    expect(regionText()).not.toContain(LOAD_FAILED);
    expect(within(region()).queryByRole("button", { name: RETRY_NAME })).toBeNull();
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it('a failed models load also shows "Could not load the configuration" and "Retry", and Retry recovers — DoD-8', async () => {
    const user = newUser();
    const backend = stubBackend({
      config: () => jsonResponse(dod1Configuration(), 200),
      models: () => serverError(),
    });
    renderSection();
    await flush();

    await waitFor(() => {
      expect(regionText()).toContain(LOAD_FAILED);
    });
    expect(queryModelSelect()).toBeNull();

    backend.routes.models = () => modelsAnswer([MODEL_A, MODEL_B]);
    await user.click(within(region()).getByRole("button", { name: RETRY_NAME }));
    await flush();

    expect(configGets(backend.calls)).toHaveLength(2);
    expect(modelsGets(backend.calls)).toHaveLength(2);
    await waitFor(() => {
      expect(queryModelSelect()).not.toBeNull();
    });
    expect(shownModel()).toBe(LABEL_A);
  });
});
