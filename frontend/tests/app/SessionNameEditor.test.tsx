// Feature 034 — session-names, step 005: the inline session name editor (DoD-8, plus the
// Enter-then-blur clause of DoD-4 and the inline-failure clause of DoD-6 seen through the editor).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done and
// DEC-034-11: a single-line text input labelled "Session name", pre-filled from the draft and
// focused on mount; typing updates the draft; Enter and blur commit; Escape closes with no
// request; the error renders inline under the input; the input is read-only while pending.
// Bindings come from the frozen `### Step 005` skeleton record: the component takes
// `{ state, onCommit }`; Enter and blur call `onCommit`; Escape closes through `cancelRename`;
// "closed" means `state.editingId === null`.
//
// Harness conventions:
// - The editor renders inside `AppProviders`, so the Mantine notifications outlet exists and
//   "no notification" is observable through `.mantine-Notification-root`. `notifyFailure` is not
//   mocked: the clause is about what the user is shown.
// - A sibling "Elsewhere" button gives blur a real focus target (clicking it moves focus away).
// - `fetch` is stubbed per test; every request is logged as "METHOD /path".
// - Most tests pass a spy as `onCommit` (the host's wiring); the integration tests wire it to
//   the real `commitRename`, as a host does, to observe the request count.
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runInAction } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionNameEditor } from "../../src/app/SessionNameEditor";
import type { Session } from "../../src/app/sessionsApi";
import { beginRename, commitRename, SessionRenameState } from "../../src/app/sessionRenameState";
import { SessionsState } from "../../src/app/sessionsState";
import { AppProviders } from "../../src/shared/AppProviders";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// ---------------------------------------------------------------- fixtures
const LABEL = "Session name";
const FAILURE_SENTENCE = "Could not rename the session.";
const NOTIFICATION = ".mantine-Notification-root";

const SESSION_ID = "7270000000000000042";
const STAMP = "2026-03-14T08:00:00.000000+00:00";
const RENAMED_AT = "2026-04-06T12:00:00.000000+00:00";

const NAMED: Session = {
  id: SESSION_ID,
  character_id: "7250000000000000001",
  setup_id: null,
  setup_name: null,
  name: "Harbour Night",
  archived_at: null,
  last_used_at: STAMP,
  created_at: STAMP,
  updated_at: STAMP,
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------- harness
function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

/** Stubs fetch with `answer`; returns the log of "METHOD /path" lines. */
function stubFetch(answer: () => Promise<Response>): string[] {
  const log: string[] = [];
  const impl: FetchFn = (input, init) => {
    log.push(`${requestMethod(input, init)} ${requestUrl(input).pathname}`);
    return answer();
  };
  vi.stubGlobal("fetch", vi.fn<FetchFn>(impl));
  return log;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

/** A rename state already open on NAMED, as a host's rename button would leave it. */
function openState(): SessionRenameState {
  const state = new SessionRenameState();
  beginRename(state, NAMED);
  return state;
}

function renderEditor(state: SessionRenameState, onCommit: () => void): void {
  render(
    <AppProviders>
      <SessionNameEditor state={state} onCommit={onCommit} />
      <button type="button">Elsewhere</button>
    </AppProviders>,
  );
}

function editorInput(): HTMLInputElement {
  return screen.getByRole("textbox", { name: LABEL }) as HTMLInputElement;
}

// ---------------------------------------------------------------------------
describe("SessionNameEditor — the input", () => {
  it("is a single-line text input labelled Session name — S034_005_DoD8", () => {
    renderEditor(openState(), vi.fn());
    const input = editorInput();
    expect(input.tagName).toBe("INPUT");
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
  });

  it("is pre-filled from the draft — S034_005_DoD8", () => {
    renderEditor(openState(), vi.fn());
    expect(editorInput()).toHaveValue("Harbour Night");
  });

  it("is empty for a never-renamed session — S034_005_DoD8", () => {
    const state = new SessionRenameState();
    beginRename(state, { ...NAMED, name: null });
    renderEditor(state, vi.fn());
    expect(editorInput()).toHaveValue("");
  });

  it("is focused on mount — S034_005_DoD8", () => {
    renderEditor(openState(), vi.fn());
    expect(editorInput()).toHaveFocus();
  });

  it("typing updates the state's draft — S034_005_DoD8", async () => {
    const user = userEvent.setup();
    const state = openState();
    renderEditor(state, vi.fn());
    await user.clear(editorInput());
    await user.type(editorInput(), "Dockside Truce");
    expect(state.draft).toBe("Dockside Truce");
    expect(editorInput()).toHaveValue("Dockside Truce");
  });

  it("is read-only while a commit is pending — S034_005_DoD8", () => {
    const state = openState();
    runInAction(() => {
      state.pending = true;
    });
    renderEditor(state, vi.fn());
    expect(editorInput()).toHaveAttribute("readonly");
  });

  it("typing while pending does not change the draft — S034_005_DoD8", async () => {
    const user = userEvent.setup();
    const state = openState();
    runInAction(() => {
      state.pending = true;
    });
    renderEditor(state, vi.fn());
    await user.type(editorInput(), "xyz");
    expect(state.draft).toBe("Harbour Night");
  });
});

// ---------------------------------------------------------------------------
describe("SessionNameEditor — keys and blur", () => {
  it("Enter commits — S034_005_DoD8", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn<() => void>();
    renderEditor(openState(), onCommit);
    await user.type(editorInput(), " II");
    await user.keyboard("{Enter}");
    expect(onCommit).toHaveBeenCalled();
  });

  it("blur commits — S034_005_DoD8", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn<() => void>();
    renderEditor(openState(), onCommit);
    await user.type(editorInput(), " II");
    expect(onCommit).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Elsewhere" }));
    expect(onCommit).toHaveBeenCalled();
  });

  it("typing alone does not commit — S034_005_DoD8", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn<() => void>();
    renderEditor(openState(), onCommit);
    await user.type(editorInput(), " II");
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("Escape closes the editor without committing and sends no request — S034_005_DoD8", async () => {
    const user = userEvent.setup();
    const log = stubFetch(() => Promise.resolve(jsonResponse(NAMED, 200)));
    const onCommit = vi.fn<() => void>();
    const state = openState();
    renderEditor(state, onCommit);
    await user.type(editorInput(), " changed");
    await user.keyboard("{Escape}");
    expect(state.editingId).toBeNull();
    expect(onCommit).not.toHaveBeenCalled();
    expect(log).toEqual([]);
  });

  it("Enter through the real commit sends exactly one PATCH /api/sessions/<id> — S034_005_DoD8", async () => {
    const user = userEvent.setup();
    const returned: Session = { ...NAMED, name: "Harbour Night II", updated_at: RENAMED_AT };
    const log = stubFetch(() => Promise.resolve(jsonResponse(returned, 200)));
    const sessions = new SessionsState();
    runInAction(() => {
      sessions.sessions = [{ ...NAMED }];
      sessions.status = "ready";
    });
    const state = openState();
    renderEditor(state, () => void commitRename(state, sessions));
    await user.type(editorInput(), " II");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(state.editingId).toBeNull());
    expect(log).toEqual([`PATCH /api/sessions/${SESSION_ID}`]);
    expect(sessions.sessions[0].name).toBe("Harbour Night II");
  });

  it("Enter followed by blur while pending sends one request — S034_005_DoD4", async () => {
    const user = userEvent.setup();
    const answer = deferred<Response>();
    const log = stubFetch(() => answer.promise);
    const sessions = new SessionsState();
    runInAction(() => {
      sessions.sessions = [{ ...NAMED }];
      sessions.status = "ready";
    });
    const state = openState();
    renderEditor(state, () => void commitRename(state, sessions));
    await user.type(editorInput(), " II");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(state.pending).toBe(true));
    await user.click(screen.getByRole("button", { name: "Elsewhere" }));
    expect(log).toHaveLength(1);
    await act(async () => {
      answer.resolve(jsonResponse({ ...NAMED, name: "Harbour Night II", updated_at: RENAMED_AT }, 200));
      await answer.promise;
    });
    await waitFor(() => expect(state.editingId).toBeNull());
    expect(log).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
describe("SessionNameEditor — the inline error", () => {
  it("renders the state's error under the input — S034_005_DoD8", () => {
    const state = openState();
    runInAction(() => {
      state.error = FAILURE_SENTENCE;
    });
    renderEditor(state, vi.fn());
    const input = editorInput();
    const error = screen.getByText(FAILURE_SENTENCE);
    expect(input.compareDocumentPosition(error) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("shows no error text while the error is null — S034_005_DoD8", () => {
    renderEditor(openState(), vi.fn());
    expect(screen.queryByText(FAILURE_SENTENCE)).toBeNull();
    expect(editorInput()).not.toHaveAttribute("aria-invalid", "true");
  });

  it("an error written after mount appears (the editor observes the state) — S034_005_DoD8", () => {
    const state = openState();
    renderEditor(state, vi.fn());
    act(() => {
      runInAction(() => {
        state.error = FAILURE_SENTENCE;
      });
    });
    expect(screen.getByText(FAILURE_SENTENCE)).toBeInTheDocument();
  });

  it("a failed commit shows the sentence inline, keeps the typed text and raises no notification — S034_005_DoD6", async () => {
    const user = userEvent.setup();
    stubFetch(() =>
      Promise.resolve(
        jsonResponse({ error: { code: "internal_error", message: "boom zq-500", detail: {} } }, 500),
      ),
    );
    const sessions = new SessionsState();
    runInAction(() => {
      sessions.sessions = [{ ...NAMED }];
      sessions.status = "ready";
    });
    const state = openState();
    renderEditor(state, () => void commitRename(state, sessions));
    await user.type(editorInput(), " II");
    await user.keyboard("{Enter}");
    expect(await screen.findByText(FAILURE_SENTENCE)).toBeInTheDocument();
    expect(editorInput()).toHaveValue("Harbour Night II");
    expect(state.editingId).toBe(SESSION_ID);
    expect(sessions.sessions[0].name).toBe("Harbour Night");
    expect(document.querySelectorAll(NOTIFICATION)).toHaveLength(0);
  });
});
