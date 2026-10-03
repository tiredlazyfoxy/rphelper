// Feature 017, step 010 — the session configuration modal (DoD-1..DoD-8).
// DoD-9 is [manual/live] and carries no test.
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 010.context.md ("Inherited line inputs", "Scoping in tests") and context.md: D18 (fresh
// draft per open, an explicit Inherit per setting, Save sends only changed keys with `null`
// for Inherit, no change → nothing sent and close, no model control), D19 (failures render
// in place, no notification), the Wire contract (`PATCH /api/sessions/{id}/configuration`,
// `Setting<T>` and its level rules) and the UI strings table.
//
// Recognition conventions (for the verifier):
// - Mantine `Modal` renders in a portal: the dialog is found through `screen` by role
//   "dialog" and name "Session configuration"; everything else is scoped `within` it.
// - Each `SegmentedControl` is a radio group named by its label; its options are radios
//   found inside that group ("Inherit" appears six times).
// - Inherited lines are asserted on the dialog's whitespace-normalised text, because the
//   prompt line is "Inherited from the character:" *followed by* the prompt, which may be a
//   separate element.
// - A notification is `.mantine-Notification-root` (the repo's convention); `notifyFailure`
//   is also spied. 017 has no notification anywhere (D19), so both stay empty.
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelRef, SessionConfiguration, Setting } from "../../src/app/configurationApi";
import { SessionConfigModal } from "../../src/app/SessionConfigModal";
import { AppProviders } from "../../src/shared/AppProviders";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; search: string; body: unknown };
type User = ReturnType<typeof userEvent.setup>;

// ---------------------------------------------------------------- the spec's names
const SESSION_ID = "7250000000000000101";
const CONFIG_PATH = `/api/sessions/${SESSION_ID}/configuration`;

const TITLE = "Session configuration";
const SYSTEM_PROMPT = "System prompt";
const MEMO_SEARCH = "Memo search";
const SESSION_SEARCH = "Session search";
const WEB_SEARCH = "Web search";
const RP_LANGUAGE = "RP language";
const PREFERRED_LANGUAGE = "Preferred language";
const ALL_SOURCE_CONTROLS = [
  SYSTEM_PROMPT,
  MEMO_SEARCH,
  SESSION_SEARCH,
  WEB_SEARCH,
  RP_LANGUAGE,
  PREFERRED_LANGUAGE,
];

const SESSION_PROMPT_INPUT = "Session system prompt";
const SESSION_RP_INPUT = "Session RP language";
const SESSION_PREFERRED_INPUT = "Session preferred language";

const LANGUAGE_REQUIRED = "Enter a language, or choose Inherit.";
const SAVE_FAILED = "Could not save the session configuration.";
const NO_PROMPT_TO_INHERIT = "Nothing to inherit: the character has no system prompt.";
const NO_LANGUAGE_TO_INHERIT = "Nothing to inherit: no default in your settings.";

const NOTIFICATION = ".mantine-Notification-root";

// ---------------------------------------------------------------- payload builders
const CAPTURED: ModelRef = { server_id: "7250000000000000301", model_name: "alpha-13b" };

/** System prompt: inherits from `character` (else inherited null, level null). */
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

/** Language: inherits from `user` (else null). */
function languageSetting(session: string | null, inherited: string | null): Setting<string> {
  return {
    session,
    inherited,
    inherited_level: inherited === null ? null : "user",
    value: session ?? inherited,
    level: session !== null ? "session" : inherited !== null ? "user" : null,
  };
}

/** DoD-1's configuration: everything inherited — character prompt "Stay in character.",
 * character memo search off, user RP language "Japanese", nothing else set. */
function inheritedConfiguration(): SessionConfiguration {
  return {
    model: { ...CAPTURED },
    system_prompt: promptSetting(null, "Stay in character."),
    tool_memo_search: toolSetting(null, false),
    tool_session_search: toolSetting(null),
    tool_web_search: toolSetting(null),
    rp_language: languageSetting(null, "Japanese"),
    preferred_language: languageSetting(null, null),
  };
}

/** DoD-3's configuration: the session overrides web search (off) and RP language ("French"). */
function overriddenConfiguration(): SessionConfiguration {
  return {
    ...inheritedConfiguration(),
    tool_web_search: toolSetting(false),
    rp_language: languageSetting("French", "Japanese"),
  };
}

/** DoD-8's configuration: the character supplies nothing at all. */
function bareConfiguration(): SessionConfiguration {
  return {
    model: null,
    system_prompt: promptSetting(null, null),
    tool_memo_search: toolSetting(null),
    tool_session_search: toolSetting(null),
    tool_web_search: toolSetting(null),
    rp_language: languageSetting(null, "Japanese"),
    preferred_language: languageSetting(null, null),
  };
}

/** What the server answers DoD-2's save with. */
function servedAfterPrompt(): SessionConfiguration {
  return {
    ...inheritedConfiguration(),
    system_prompt: promptSetting("Be terse.", "Stay in character."),
  };
}

/** What the server answers DoD-3's save with. */
function servedAfterClear(): SessionConfiguration {
  return inheritedConfiguration();
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

function serverError(): Response {
  return jsonResponse(
    { error: { code: "internal_error", message: "kv-19 backend prose.", detail: {} } },
    500,
  );
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

/** Answers only `PATCH <CONFIG_PATH>` (no query) with `answer`; anything else is a 500.
 * Every request is recorded. */
function stubPatch(answer: () => Response | Promise<Response>) {
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
    if (request.method === "PATCH" && request.path === CONFIG_PATH && request.search === "") {
      return answer();
    }
    return serverError();
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

function patches(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "PATCH" && call.path === CONFIG_PATH);
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

// ---------------------------------------------------------------- render
function renderModal(configuration: SessionConfiguration) {
  const onClose = vi.fn<() => void>();
  const onSaved = vi.fn<(saved: SessionConfiguration) => void>();
  const tree = (opened: boolean) => (
    <AppProviders>
      <SessionConfigModal
        opened={opened}
        sessionId={SESSION_ID}
        configuration={configuration}
        onClose={onClose}
        onSaved={onSaved}
      />
    </AppProviders>
  );
  const view = render(tree(true));
  const setOpened = (opened: boolean) => view.rerender(tree(opened));
  return { onClose, onSaved, view, setOpened };
}

// ---------------------------------------------------------------- queries
function dialog(): HTMLElement {
  return screen.getByRole("dialog", { name: TITLE });
}

async function openedDialog(): Promise<HTMLElement> {
  return screen.findByRole("dialog", { name: TITLE });
}

function group(label: string): HTMLElement {
  return within(dialog()).getByRole("radiogroup", { name: label });
}

function radio(groupLabel: string, option: string): HTMLElement {
  return within(group(groupLabel)).getByRole("radio", { name: option });
}

function textbox(label: string): HTMLElement {
  return within(dialog()).getByRole("textbox", { name: label });
}

function queryTextbox(label: string): HTMLElement | null {
  return within(dialog()).queryByRole("textbox", { name: label });
}

function button(name: string): HTMLElement {
  return within(dialog()).getByRole("button", { name });
}

/** The dialog's visible text with whitespace runs collapsed. */
function dialogText(): string {
  return (dialog().textContent ?? "").replace(/\s+/g, " ");
}

/** Every tool inherited line, in document order (canonical spacing). Adjacent elements may
 * glue their text together, so each alternative matches only the line's own words. */
function toolLines(): string[] {
  const pattern = /Inherited from the character: ?(?:off|on)|Inherited: ?on \(default\)/g;
  return (dialogText().match(pattern) ?? []).map((line) => line.replace(/: ?/, ": "));
}

/** Every language inherited line, in document order (canonical spacing). The fixtures'
 * only user-level language is "Japanese". */
function languageLines(): string[] {
  const pattern =
    /Inherited from your settings: ?Japanese|Nothing to inherit: no default in your settings\./g;
  return (dialogText().match(pattern) ?? []).map((line) => line.replace(/: ?/, ": "));
}

function notificationsShown(): Element[] {
  return Array.from(document.querySelectorAll(NOTIFICATION));
}

async function choose(user: User, groupLabel: string, option: string): Promise<void> {
  await user.click(radio(groupLabel, option));
}

async function typeInto(user: User, element: HTMLElement, text: string): Promise<void> {
  await user.clear(element);
  await user.type(element, text);
}

// ===========================================================================
describe("opening over an all-inherited configuration", () => {
  it('shows the "Session configuration" dialog with every source control on Inherit and no session input — DoD-1', async () => {
    stubPatch(() => jsonResponse(servedAfterPrompt(), 200));
    renderModal(inheritedConfiguration());
    await openedDialog();

    for (const label of ALL_SOURCE_CONTROLS) {
      expect(radio(label, "Inherit")).toBeChecked();
    }
    expect(queryTextbox(SESSION_PROMPT_INPUT)).toBeNull();
    expect(queryTextbox(SESSION_RP_INPUT)).toBeNull();
    expect(queryTextbox(SESSION_PREFERRED_INPUT)).toBeNull();
  });

  it("offers Inherit / Set for the text settings and Inherit / On / Off for the tools — DoD-1", async () => {
    stubPatch(() => jsonResponse(servedAfterPrompt(), 200));
    renderModal(inheritedConfiguration());
    await openedDialog();

    for (const label of [SYSTEM_PROMPT, RP_LANGUAGE, PREFERRED_LANGUAGE]) {
      expect(within(group(label)).getAllByRole("radio")).toHaveLength(2);
      for (const option of ["Inherit", "Set"]) {
        expect(radio(label, option)).toBeInTheDocument();
      }
    }
    for (const label of [MEMO_SEARCH, SESSION_SEARCH, WEB_SEARCH]) {
      expect(within(group(label)).getAllByRole("radio")).toHaveLength(3);
      for (const option of ["Inherit", "On", "Off"]) {
        expect(radio(label, option)).toBeInTheDocument();
      }
    }
  });

  it('shows "Inherited from the character:" followed by the character\'s prompt — DoD-1', async () => {
    stubPatch(() => jsonResponse(servedAfterPrompt(), 200));
    renderModal(inheritedConfiguration());
    await openedDialog();

    expect(dialogText()).toMatch(/Inherited from the character: ?Stay in character\./);
    expect(dialogText()).not.toContain(NO_PROMPT_TO_INHERIT);
  });

  it('shows the memo search line "…character: off" then "Inherited: on (default)" for session and web search — DoD-1', async () => {
    stubPatch(() => jsonResponse(servedAfterPrompt(), 200));
    renderModal(inheritedConfiguration());
    await openedDialog();

    expect(toolLines()).toEqual([
      "Inherited from the character: off",
      "Inherited: on (default)",
      "Inherited: on (default)",
    ]);
  });

  it('shows "Inherited from your settings: Japanese" for RP language and the nothing-to-inherit line for the preferred language — DoD-1', async () => {
    stubPatch(() => jsonResponse(servedAfterPrompt(), 200));
    renderModal(inheritedConfiguration());
    await openedDialog();

    expect(dialogText()).toContain("Inherited from your settings: Japanese");
    expect(languageLines()).toEqual([
      "Inherited from your settings: Japanese",
      NO_LANGUAGE_TO_INHERIT,
    ]);
  });
});

// ===========================================================================
describe("setting the session system prompt", () => {
  it('choosing "Set" shows "Session system prompt" prefilled with the inherited prompt — DoD-2', async () => {
    stubPatch(() => jsonResponse(servedAfterPrompt(), 200));
    const user = newUser();
    renderModal(inheritedConfiguration());
    await openedDialog();

    await choose(user, SYSTEM_PROMPT, "Set");

    expect(radio(SYSTEM_PROMPT, "Set")).toBeChecked();
    expect(textbox(SESSION_PROMPT_INPUT)).toHaveValue("Stay in character.");
  });

  it('typing "Be terse." and pressing Save sends exactly {"system_prompt":"Be terse."}, then onSaved gets the served configuration and onClose follows — DoD-2', async () => {
    const served = servedAfterPrompt();
    const { calls } = stubPatch(() => jsonResponse(served, 200));
    const user = newUser();
    const { onSaved, onClose } = renderModal(inheritedConfiguration());
    await openedDialog();

    await choose(user, SYSTEM_PROMPT, "Set");
    await typeInto(user, textbox(SESSION_PROMPT_INPUT), "Be terse.");
    await user.click(button("Save"));
    await flush();

    expect(calls).toHaveLength(1);
    const sent = patches(calls);
    expect(sent).toHaveLength(1);
    expect(sent[0].body).toEqual({ system_prompt: "Be terse." });

    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onSaved).toHaveBeenCalledWith(served);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onSaved.mock.invocationCallOrder[0]).toBeLessThan(onClose.mock.invocationCallOrder[0]);
  });
});

// ===========================================================================
describe("clearing session overrides back to Inherit", () => {
  it('shows the web search override as "Off" and the RP language as "Set" with "French" — DoD-3', async () => {
    stubPatch(() => jsonResponse(servedAfterClear(), 200));
    renderModal(overriddenConfiguration());
    await openedDialog();

    expect(radio(WEB_SEARCH, "Off")).toBeChecked();
    expect(radio(WEB_SEARCH, "Inherit")).not.toBeChecked();
    expect(radio(RP_LANGUAGE, "Set")).toBeChecked();
    expect(textbox(SESSION_RP_INPUT)).toHaveValue("French");
  });

  it('switching both to Inherit and saving sends exactly {"tool_web_search":null,"rp_language":null} — DoD-3', async () => {
    const served = servedAfterClear();
    const { calls } = stubPatch(() => jsonResponse(served, 200));
    const user = newUser();
    const { onSaved, onClose } = renderModal(overriddenConfiguration());
    await openedDialog();

    await choose(user, WEB_SEARCH, "Inherit");
    await choose(user, RP_LANGUAGE, "Inherit");
    expect(queryTextbox(SESSION_RP_INPUT)).toBeNull();
    await user.click(button("Save"));
    await flush();

    expect(calls).toHaveLength(1);
    const sent = patches(calls);
    expect(sent).toHaveLength(1);
    expect(sent[0].body).toEqual({ tool_web_search: null, rp_language: null });
    expect(onSaved).toHaveBeenCalledWith(served);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

// ===========================================================================
describe("a Set language with no text", () => {
  it('shows "Enter a language, or choose Inherit." and disables Save; typing a value enables it — DoD-4', async () => {
    const { mock } = stubPatch(() => jsonResponse(inheritedConfiguration(), 200));
    const user = newUser();
    renderModal(inheritedConfiguration());
    await openedDialog();

    await choose(user, PREFERRED_LANGUAGE, "Set");
    const input = textbox(SESSION_PREFERRED_INPUT);
    expect(input).toHaveValue("");
    expect(within(dialog()).getByText(LANGUAGE_REQUIRED)).toBeInTheDocument();
    expect(button("Save")).toBeDisabled();

    await user.type(input, "German");

    expect(button("Save")).toBeEnabled();
    expect(within(dialog()).queryByText(LANGUAGE_REQUIRED)).toBeNull();
    expect(mock).not.toHaveBeenCalled();
  });
});

// ===========================================================================
describe("Save with nothing changed, and Cancel", () => {
  it("Save with nothing changed sends no request, calls onSaved with the original configuration and closes — DoD-5", async () => {
    const { mock } = stubPatch(() => jsonResponse(servedAfterPrompt(), 200));
    const user = newUser();
    const original = inheritedConfiguration();
    const { onSaved, onClose } = renderModal(original);
    await openedDialog();

    await user.click(button("Save"));
    await flush();

    expect(mock).not.toHaveBeenCalled();
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onSaved).toHaveBeenCalledWith(inheritedConfiguration());
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("Cancel sends nothing and calls onClose only — DoD-5", async () => {
    const { mock } = stubPatch(() => jsonResponse(servedAfterPrompt(), 200));
    const user = newUser();
    const { onSaved, onClose } = renderModal(inheritedConfiguration());
    await openedDialog();

    await choose(user, SYSTEM_PROMPT, "Set");
    await typeInto(user, textbox(SESSION_PROMPT_INPUT), "Be terse.");
    await user.click(button("Cancel"));
    await flush();

    expect(mock).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onSaved).not.toHaveBeenCalled();
  });
});

// ===========================================================================
describe("a failed save", () => {
  it("shows the save-failure sentence in the modal, keeps the typed values, calls neither callback and notifies nothing — DoD-6", async () => {
    const { calls } = stubPatch(() => serverError());
    const user = newUser();
    const { onSaved, onClose } = renderModal(inheritedConfiguration());
    await openedDialog();

    await choose(user, SYSTEM_PROMPT, "Set");
    await typeInto(user, textbox(SESSION_PROMPT_INPUT), "Be terse.");
    await choose(user, MEMO_SEARCH, "On");
    await user.click(button("Save"));
    await flush();

    expect(patches(calls)).toHaveLength(1);
    expect(within(dialog()).getByText(SAVE_FAILED)).toBeInTheDocument();
    expect(radio(SYSTEM_PROMPT, "Set")).toBeChecked();
    expect(textbox(SESSION_PROMPT_INPUT)).toHaveValue("Be terse.");
    expect(radio(MEMO_SEARCH, "On")).toBeChecked();
    expect(onSaved).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(notificationsShown()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("a transport failure behaves the same: sentence in the modal, no callback, no notification — DoD-6", async () => {
    const user = newUser();
    const mock = vi.fn<FetchFn>(async () => {
      throw new TypeError("Failed to fetch");
    });
    vi.stubGlobal("fetch", mock);
    const { onSaved, onClose } = renderModal(inheritedConfiguration());
    await openedDialog();

    await choose(user, WEB_SEARCH, "Off");
    await user.click(button("Save"));
    await flush();

    expect(mock).toHaveBeenCalledTimes(1);
    expect(within(dialog()).getByText(SAVE_FAILED)).toBeInTheDocument();
    expect(radio(WEB_SEARCH, "Off")).toBeChecked();
    expect(onSaved).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(notificationsShown()).toEqual([]);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
describe("a fresh draft per open", () => {
  it("closing after typing and reopening shows the controls seeded from the configuration prop again — DoD-7", async () => {
    const { mock } = stubPatch(() => jsonResponse(servedAfterPrompt(), 200));
    const user = newUser();
    const { setOpened, onSaved } = renderModal(inheritedConfiguration());
    await openedDialog();

    await choose(user, SYSTEM_PROMPT, "Set");
    await typeInto(user, textbox(SESSION_PROMPT_INPUT), "Abandoned typing.");
    await choose(user, MEMO_SEARCH, "On");
    await choose(user, PREFERRED_LANGUAGE, "Set");
    await user.type(textbox(SESSION_PREFERRED_INPUT), "German");

    setOpened(false);
    await flush();
    setOpened(true);
    await openedDialog();
    await flush();

    for (const label of ALL_SOURCE_CONTROLS) {
      expect(radio(label, "Inherit")).toBeChecked();
    }
    expect(queryTextbox(SESSION_PROMPT_INPUT)).toBeNull();
    expect(queryTextbox(SESSION_PREFERRED_INPUT)).toBeNull();

    await choose(user, SYSTEM_PROMPT, "Set");
    expect(textbox(SESSION_PROMPT_INPUT)).toHaveValue("Stay in character.");
    expect(mock).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("reopening over a configuration with session overrides shows those overrides, not the abandoned edits — DoD-7", async () => {
    stubPatch(() => jsonResponse(servedAfterClear(), 200));
    const user = newUser();
    const { setOpened } = renderModal(overriddenConfiguration());
    await openedDialog();

    await choose(user, WEB_SEARCH, "On");
    await typeInto(user, textbox(SESSION_RP_INPUT), "Spanish");

    setOpened(false);
    await flush();
    setOpened(true);
    await openedDialog();
    await flush();

    expect(radio(WEB_SEARCH, "Off")).toBeChecked();
    expect(radio(RP_LANGUAGE, "Set")).toBeChecked();
    expect(textbox(SESSION_RP_INPUT)).toHaveValue("French");
  });
});

// ===========================================================================
describe("what the modal does not carry", () => {
  it('contains no control labelled "Model" — DoD-8', async () => {
    stubPatch(() => jsonResponse(inheritedConfiguration(), 200));
    renderModal(inheritedConfiguration());
    const opened = await openedDialog();

    expect(within(opened).queryAllByLabelText(/model/i)).toEqual([]);
    for (const role of ["combobox", "textbox", "radiogroup", "listbox", "button"] as const) {
      expect(within(opened).queryAllByRole(role, { name: /model/i })).toEqual([]);
    }
  });

  it("labels neither language control nor its session input as a character setting — DoD-8", async () => {
    stubPatch(() => jsonResponse(inheritedConfiguration(), 200));
    const user = newUser();
    renderModal(inheritedConfiguration());
    await openedDialog();

    expect(group(RP_LANGUAGE)).toBeInTheDocument();
    expect(group(PREFERRED_LANGUAGE)).toBeInTheDocument();
    const languageGroups = within(dialog())
      .getAllByRole("radiogroup")
      .filter((element) => /language/i.test(accessibleLabel(element)));
    expect(languageGroups).toHaveLength(2);
    for (const element of languageGroups) {
      expect(accessibleLabel(element)).not.toMatch(/character/i);
    }

    await choose(user, RP_LANGUAGE, "Set");
    await choose(user, PREFERRED_LANGUAGE, "Set");
    expect(textbox(SESSION_RP_INPUT)).toBeInTheDocument();
    expect(textbox(SESSION_PREFERRED_INPUT)).toBeInTheDocument();
    expect(within(dialog()).queryAllByRole("textbox", { name: /character/i })).toEqual([]);
  });

  it('the only language inherited lines name "your settings", never the character — DoD-8', async () => {
    stubPatch(() => jsonResponse(bareConfiguration(), 200));
    renderModal(bareConfiguration());
    await openedDialog();

    expect(languageLines()).toEqual([
      "Inherited from your settings: Japanese",
      NO_LANGUAGE_TO_INHERIT,
    ]);
    // With a character that supplies nothing, the only mention of "character" is the
    // system prompt's nothing-to-inherit sentence; the tools inherit the default.
    expect(dialogText()).toContain(NO_PROMPT_TO_INHERIT);
    expect(toolLines()).toEqual([
      "Inherited: on (default)",
      "Inherited: on (default)",
      "Inherited: on (default)",
    ]);
    expect(dialogText().match(/character/gi) ?? []).toHaveLength(1);
  });
});

/** The accessible label of a labelled group: `aria-label`, else the `aria-labelledby` text. */
function accessibleLabel(element: HTMLElement): string {
  const direct = element.getAttribute("aria-label");
  if (direct !== null) return direct;
  const ids = (element.getAttribute("aria-labelledby") ?? "").split(/\s+/).filter(Boolean);
  return ids.map((id) => document.getElementById(id)?.textContent ?? "").join(" ").trim();
}
