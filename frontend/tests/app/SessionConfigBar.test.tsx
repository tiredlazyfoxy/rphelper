// Feature 017, step 011 — the session header bar (DoD-1..DoD-5).
// Composer's gate (DoD-6, DoD-7) is in Composer.test.tsx; the screen mount (DoD-8..DoD-10) and
// the amended stubs (DoD-11) are in SessionScreen.test.tsx, App.test.tsx and entries.test.tsx.
// DoD-12 is [manual/live] and carries no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 011.context.md ("Test notes") and context.md: D16 (the bar's contents, the captured model as
// the picker's value, the disabled "(not enabled)" option, the disabled empty picker, load on
// bar mount), D18 (the modal's save replaces the bar's configuration with no refetch), D19 (no
// notification; failures in place), the Wire contract and the UI strings table.
//
// Recognition conventions (for the verifier):
// - The bar is the group named "Session configuration"; everything of the bar is scoped inside
//   it. The tool indicators are the group "Tools" inside it; badge text is asserted exactly.
// - The picker is the field labelled "Model" (found as a combobox, else a textbox, else by
//   label — the SessionsSection.test.tsx precedent). Its shown value is the input's value; its
//   placeholder is the input's placeholder attribute.
// - Mantine `Select` options render in a portal: they are read off `screen` by role "option".
//   An option counts as disabled when it carries `aria-disabled="true"`, a `disabled`
//   attribute, or Mantine's `data-combobox-disabled` / `data-disabled` marker.
// - The modal is the dialog named "Session configuration" (step 010); its tool switches are
//   radio groups named by their labels.
// - A notification is `.mantine-Notification-root`; `notifyFailure` is also mocked and spied.
// - Stubs key on the exact method + pathname + query (context.md "Test conventions").
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EnabledModel, ModelRef, SessionConfiguration, Setting } from "../../src/app/configurationApi";
import { SessionConfigBar } from "../../src/app/SessionConfigBar";
import { SessionConfigState } from "../../src/app/sessionConfigState";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };
type User = ReturnType<typeof userEvent.setup>;
type Answer = () => Response | Promise<Response>;

// ---------------------------------------------------------------- the spec's names
const BAR_NAME = "Session configuration";
const TOOLS_NAME = "Tools";
const MODEL_LABEL = "Model";
const GEAR_NAME = "Session configuration";
const DIALOG_NAME = "Session configuration";
const RETRY_NAME = "Retry";
const LOAD_FAILED = "Could not load the session configuration";
const NOT_ENABLED_FAILURE = "That model is no longer enabled.";
const CHOOSE_PLACEHOLDER = "Choose a model";
const EMPTY_PLACEHOLDER = "No model is enabled";
const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- fixtures
const SESSION_ID = "7250000000000000101";
const CONFIG_PATH = `/api/sessions/${SESSION_ID}/configuration`;
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

function promptSetting(session: string | null, inherited: string | null): Setting<string> {
  return {
    session,
    inherited,
    inherited_level: inherited === null ? null : "character",
    value: session ?? inherited,
    level: session !== null ? "session" : inherited !== null ? "character" : null,
  };
}

/** Tool: inherits from `character` when it sets one, else `true` at level `default`. */
function toolSetting(session: boolean | null, character: boolean | null = null): Setting<boolean> {
  const inherited = character ?? true;
  const inheritedLevel = character === null ? "default" : "character";
  return {
    session,
    inherited,
    inherited_level: inheritedLevel,
    value: session ?? inherited,
    level: session !== null ? "session" : inheritedLevel,
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

/**
 * DoD-1's configuration: captured model A on S1; memo search on (default), session search off
 * (the character sets it off), web search on (the session sets it on).
 */
function configuration(model: ModelRef | null = REF_A): SessionConfiguration {
  return {
    model: model === null ? null : { ...model },
    system_prompt: promptSetting(null, null),
    tool_memo_search: toolSetting(null),
    tool_session_search: toolSetting(null, false),
    tool_web_search: toolSetting(true),
    rp_language: languageSetting(null, null),
    preferred_language: languageSetting(null, null),
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

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number, detail: unknown = {}): Response {
  return jsonResponse({ error: { code, message: "zq-41 backend prose.", detail } }, status);
}

function serverError(): Response {
  return envelope("internal_error", 500);
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

function renderBar() {
  const state = new SessionConfigState(SESSION_ID);
  const view = render(
    <AppProviders>
      <SessionConfigBar state={state} />
    </AppProviders>,
  );
  return { state, view };
}

// ---------------------------------------------------------------- queries
function bar(): HTMLElement {
  return screen.getByRole("group", { name: BAR_NAME });
}

function toolsGroup(): HTMLElement {
  return within(bar()).getByRole("group", { name: TOOLS_NAME });
}

function modelSelect(): HTMLElement {
  const scope = within(bar());
  return (
    scope.queryByRole("combobox", { name: MODEL_LABEL }) ??
    scope.queryByRole("textbox", { name: MODEL_LABEL }) ??
    scope.getByLabelText(MODEL_LABEL)
  );
}

/** What the "Model" picker currently displays. */
function shownModel(): string {
  const element = modelSelect();
  const shown = element instanceof HTMLInputElement ? element.value : element.textContent ?? "";
  return shown.trim();
}

function placeholderOf(element: HTMLElement): string | null {
  return element.getAttribute("placeholder");
}

function gearButton(): HTMLElement {
  return within(bar()).getByRole("button", { name: GEAR_NAME });
}

function optionTexts(): string[] {
  return screen.queryAllByRole("option").map((option) => (option.textContent ?? "").trim());
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

function badgeTexts(): string[] {
  const text = (toolsGroup().textContent ?? "").replace(/\s+/g, " ");
  return ["Memo search", "Session search", "Web search"].map((tool) => {
    const match = new RegExp(`${tool}: (on|off)`).exec(text);
    return match === null ? `${tool}: <missing>` : match[0];
  });
}

function notificationsShown(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION));
}

// ---------------------------------------------------------------------------
describe("the bar over a loaded configuration and models (UC-077, US-062.AC-1, D16)", () => {
  it('the "Model" picker shows "A (S1)"; opening it lists "A (S1)" then "B (S2)"; Tools shows each resolved value; the gear is enabled — DoD-1', async () => {
    const user = newUser();
    const { calls } = stubBackend({
      config: () => jsonResponse(configuration(REF_A), 200),
      models: () => jsonResponse({ models: [MODEL_A, MODEL_B] }, 200),
    });
    renderBar();
    await flush();

    expect(shownModel()).toBe(LABEL_A);

    const tools = toolsGroup();
    expect(within(tools).getByText("Memo search: on")).toBeInTheDocument();
    expect(within(tools).getByText("Session search: off")).toBeInTheDocument();
    expect(within(tools).getByText("Web search: on")).toBeInTheDocument();
    expect(badgeTexts()).toEqual(["Memo search: on", "Session search: off", "Web search: on"]);

    expect(gearButton()).toBeEnabled();

    await openPicker(user);
    expect(optionTexts()).toEqual([LABEL_A, LABEL_B]);

    // Loaded on mount: exactly one read of each.
    expect(configGets(calls)).toHaveLength(1);
    expect(modelsGets(calls)).toHaveLength(1);
    expect(configPatches(calls)).toEqual([]);
  });

  it("the options follow the served order, not a sorted one — DoD-1", async () => {
    const user = newUser();
    stubBackend({
      config: () => jsonResponse(configuration(REF_A), 200),
      models: () => jsonResponse({ models: [MODEL_B, MODEL_A] }, 200),
    });
    renderBar();
    await flush();

    await openPicker(user);
    expect(optionTexts()).toEqual([LABEL_B, LABEL_A]);
  });

  it("the gear stays disabled until the configuration is ready — DoD-1", async () => {
    const gate = deferred<Response>();
    stubBackend({
      config: () => gate.promise,
      models: () => jsonResponse({ models: [MODEL_A, MODEL_B] }, 200),
    });
    renderBar();
    await flush();

    expect(gearButton()).toBeDisabled();
    expect(within(bar()).queryByRole("group", { name: TOOLS_NAME })).toBeNull();

    gate.resolve(jsonResponse(configuration(REF_A), 200));
    await flush();

    expect(gearButton()).toBeEnabled();
    expect(within(toolsGroup()).getByText("Web search: on")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
describe("choosing a model in the picker (US-105.AC-1; never optimistic)", () => {
  it('choosing "B (S2)" PATCHes exactly {"model":{…B…}}; while pending the picker is disabled and shows "A (S1)"; after the 200 it shows "B (S2)" — DoD-2', async () => {
    const user = newUser();
    const pending = deferred<Response>();
    const { calls } = stubBackend({
      config: () => jsonResponse(configuration(REF_A), 200),
      models: () => jsonResponse({ models: [MODEL_A, MODEL_B] }, 200),
      patch: () => pending.promise,
    });
    renderBar();
    await flush();
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
      pending.resolve(jsonResponse(configuration(REF_B), 200));
    });
    await flush();

    expect(shownModel()).toBe(LABEL_B);
    expect(modelSelect()).toBeEnabled();
    expect(configPatches(calls)).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
describe("the picker's placeholder, unknown captured model and empty list (US-106, US-107, D16)", () => {
  it('captured model null with models listed: the picker shows no value and the placeholder "Choose a model" — DoD-3', async () => {
    stubBackend({
      config: () => jsonResponse(configuration(null), 200),
      models: () => jsonResponse({ models: [MODEL_A, MODEL_B] }, 200),
    });
    renderBar();
    await flush();

    const picker = modelSelect();
    expect(shownModel()).toBe("");
    expect(placeholderOf(picker)).toBe(CHOOSE_PLACEHOLDER);
    expect(picker).toBeEnabled();
  });

  it('captured model absent from the list: the picker shows "A (not enabled)" and that option is disabled — DoD-3', async () => {
    const user = newUser();
    const { calls } = stubBackend({
      config: () => jsonResponse(configuration(REF_A), 200),
      models: () => jsonResponse({ models: [MODEL_B] }, 200),
      patch: () => jsonResponse(configuration(REF_A), 200),
    });
    renderBar();
    await flush();

    expect(shownModel()).toBe(LABEL_A_NOT_ENABLED);

    await openPicker(user);
    expect(optionTexts()).toContain(LABEL_B);
    expect(optionTexts()).toContain(LABEL_A_NOT_ENABLED);
    expect(optionTexts()).toHaveLength(2);
    const notEnabled = screen.getByRole("option", { name: LABEL_A_NOT_ENABLED });
    expect(optionDisabled(notEnabled)).toBe(true);
    expect(optionDisabled(screen.getByRole("option", { name: LABEL_B }))).toBe(false);

    // A disabled option cannot be chosen: pressing it sends nothing.
    await user.click(notEnabled);
    await flush();
    expect(configPatches(calls)).toEqual([]);
  });

  it('the same model name on another server counts as absent: "A (not enabled)" — DoD-3', async () => {
    stubBackend({
      config: () => jsonResponse(configuration(REF_A), 200),
      models: () =>
        jsonResponse({ models: [{ server_id: S2_ID, server_name: "S2", model_name: "A" }] }, 200),
    });
    renderBar();
    await flush();

    expect(shownModel()).toBe(LABEL_A_NOT_ENABLED);
  });

  it('an empty list: the picker is disabled with the placeholder "No model is enabled" — DoD-3', async () => {
    stubBackend({
      config: () => jsonResponse(configuration(null), 200),
      models: () => jsonResponse({ models: [] }, 200),
    });
    renderBar();
    await flush();

    const picker = modelSelect();
    expect(picker).toBeDisabled();
    expect(placeholderOf(picker)).toBe(EMPTY_PLACEHOLDER);
    expect(shownModel()).toBe("");
  });
});

// ---------------------------------------------------------------------------
describe("failures render in the bar, with no notification (D10, D19)", () => {
  it('a 409 model_not_enabled on choosing shows "That model is no longer enabled.", keeps "A (S1)" and re-requests GET /api/models — DoD-4', async () => {
    const user = newUser();
    let modelsServed: EnabledModel[] = [MODEL_A, MODEL_B];
    const { calls } = stubBackend({
      config: () => jsonResponse(configuration(REF_A), 200),
      models: () => jsonResponse({ models: modelsServed }, 200),
      patch: () =>
        envelope("model_not_enabled", 409, { server_id: S2_ID, model_name: "B", level: "session" }),
    });
    renderBar();
    await flush();
    expect(modelsGets(calls)).toHaveLength(1);

    modelsServed = [MODEL_A];
    await openPicker(user);
    await chooseOption(user, LABEL_B);
    await flush();

    expect(await within(bar()).findByText(NOT_ENABLED_FAILURE)).toBeInTheDocument();
    expect(shownModel()).toBe(LABEL_A);
    await waitFor(() => {
      expect(modelsGets(calls)).toHaveLength(2);
    });
    const patchAt = calls.findIndex((call) => call.method === "PATCH" && call.path === CONFIG_PATH);
    const rereadAt = calls.map((call) => `${call.method} ${call.path}`).lastIndexOf(`GET ${MODELS_PATH}`);
    expect(rereadAt).toBeGreaterThan(patchAt);
    // The configuration itself is not re-read.
    expect(configGets(calls)).toHaveLength(1);

    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(notificationsShown()).toEqual([]);
  });

  type LoadFailure = [label: string, routes: () => Routes];

  const LOAD_FAILURES: LoadFailure[] = [
    [
      "the configuration read fails",
      () => ({
        config: serverError,
        models: () => jsonResponse({ models: [MODEL_A, MODEL_B] }, 200),
      }),
    ],
    [
      "the models read fails",
      () => ({
        config: () => jsonResponse(configuration(REF_A), 200),
        models: serverError,
      }),
    ],
    [
      "both reads fail in transport",
      () => ({
        config: () => {
          throw new TypeError("Failed to fetch");
        },
        models: () => {
          throw new TypeError("Failed to fetch");
        },
      }),
    ],
  ];

  it.each(LOAD_FAILURES)(
    'when %s, the bar shows "Could not load the session configuration" and "Retry", and Retry re-requests both — DoD-4',
    async (_label, failing) => {
      const user = newUser();
      const { calls, routes } = stubBackend(failing());
      renderBar();
      await flush();

      expect(within(bar()).getByText(LOAD_FAILED)).toBeInTheDocument();
      const retry = within(bar()).getByRole("button", { name: RETRY_NAME });
      expect(configGets(calls)).toHaveLength(1);
      expect(modelsGets(calls)).toHaveLength(1);

      routes.config = () => jsonResponse(configuration(REF_A), 200);
      routes.models = () => jsonResponse({ models: [MODEL_A, MODEL_B] }, 200);
      await user.click(retry);
      await flush();

      expect(configGets(calls)).toHaveLength(2);
      expect(modelsGets(calls)).toHaveLength(2);
      expect(within(bar()).queryByText(LOAD_FAILED)).toBeNull();
      expect(shownModel()).toBe(LABEL_A);
      expect(within(toolsGroup()).getByText("Web search: on")).toBeInTheDocument();

      expect(notifyFailureSpy).not.toHaveBeenCalled();
      expect(notificationsShown()).toEqual([]);
    },
  );
});

// ---------------------------------------------------------------------------
describe("the gear opens the session configuration modal (UC-049, D18)", () => {
  it('pressing "Session configuration" opens the dialog; saving web search off closes it and the badge reads "Web search: off" with no further GET — DoD-5', async () => {
    const user = newUser();
    const served: SessionConfiguration = { ...configuration(REF_A), tool_web_search: toolSetting(false) };
    const { calls } = stubBackend({
      config: () => jsonResponse(configuration(REF_A), 200),
      models: () => jsonResponse({ models: [MODEL_A, MODEL_B] }, 200),
      patch: () => jsonResponse(served, 200),
    });
    renderBar();
    await flush();
    expect(screen.queryByRole("dialog", { name: DIALOG_NAME })).toBeNull();

    await user.click(gearButton());
    const dialog = await screen.findByRole("dialog", { name: DIALOG_NAME });

    const webSearch = within(dialog).getByRole("radiogroup", { name: "Web search" });
    await user.click(within(webSearch).getByRole("radio", { name: "Off" }));
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await flush();

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: DIALOG_NAME })).toBeNull();
    });
    expect(within(toolsGroup()).getByText("Web search: off")).toBeInTheDocument();
    expect(within(toolsGroup()).queryByText("Web search: on")).toBeNull();

    const sent = configPatches(calls);
    expect(sent).toHaveLength(1);
    expect(sent[0].body).toEqual({ tool_web_search: false });
    const patchAt = calls.findIndex((call) => call.method === "PATCH" && call.path === CONFIG_PATH);
    expect(configGets(calls.slice(patchAt + 1))).toEqual([]);
    expect(configGets(calls)).toHaveLength(1);

    expect(notifyFailureSpy).not.toHaveBeenCalled();
    expect(notificationsShown()).toEqual([]);
  });
});
