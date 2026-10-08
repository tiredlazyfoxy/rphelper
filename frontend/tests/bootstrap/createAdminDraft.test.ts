// Feature 003, step 005 — the create-administrator draft, its pure validators and its
// effectful submit (DoD-1, DoD-2, DoD-4, DoD-5, DoD-6, DoD-7, DoD-9, DoD-10).
//
// Expected values come from the step's Interface intent and Definition of done, and from
// `context.md` D12/D13/D16. `fetch` is stubbed per test; `notifyFailure` is mocked at file
// level because spying on an ESM export is unreliable.
import { isComputedProp, isObservableProp, runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CreateAdminDraft,
  canSubmitCreateAdmin,
  createAdminClientErrors,
  submitCreateAdmin,
} from "../../src/bootstrap/createAdminDraft";
import { documentNavigation } from "../../src/shared/api";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const USERNAME = "operator-admin";
const PASSWORD = "Tq!9-correct-horse";
const DRAFT_FIELDS = ["username", "password", "confirmation", "serverErrors", "submitting"] as const;

beforeEach(() => {
  notifyFailureSpy.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

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

function envelope(code: string, message: string, status: number, detail: Record<string, unknown> = {}) {
  return () => Promise.resolve(jsonResponse({ error: { code, message, detail } }, status));
}

const created = () =>
  Promise.resolve(jsonResponse({ id: "7340032000000001", username: USERNAME, role: "admin" }, 201));

const alreadyConfigured = envelope("already_configured", "This instance is already configured.", 409);

const transportFailure = () => Promise.reject(new TypeError("Failed to fetch"));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

/** A request that only ever ends by rejecting with an AbortError when its signal aborts. */
const abortableNeverAnswers: FetchFn = (_input, init) =>
  new Promise<Response>((_resolve, reject) => {
    const signal = init?.signal;
    const abortError = () => new DOMException("The operation was aborted.", "AbortError");
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    signal?.addEventListener("abort", () => reject(abortError()));
  });

function makeDraft(fields: { username?: string; password?: string; confirmation?: string } = {}): CreateAdminDraft {
  const draft = new CreateAdminDraft();
  runInAction(() => {
    draft.username = fields.username ?? "";
    draft.password = fields.password ?? "";
    draft.confirmation = fields.confirmation ?? "";
  });
  return draft;
}

function validDraft(): CreateAdminDraft {
  return makeDraft({ username: USERNAME, password: PASSWORD, confirmation: PASSWORD });
}

function requestPath(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost").pathname;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function requestJson(init?: RequestInit): unknown {
  const raw = init?.body;
  if (typeof raw !== "string") {
    throw new Error(`request body is not a JSON string: ${String(raw)}`);
  }
  return JSON.parse(raw);
}

async function flushMicrotasks(): Promise<void> {
  for (let i = 0; i < 4; i += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

// ---------------------------------------------------------------------------
describe("createAdminClientErrors", () => {
  it("reports no error for a filled, matching draft — DoD-1", () => {
    expect(createAdminClientErrors(validDraft())).toEqual({});
  });

  it("reports a username error for an empty username — DoD-1", () => {
    const errors = createAdminClientErrors(makeDraft({ username: "", password: PASSWORD, confirmation: PASSWORD }));
    expect(errors.username).toBeTruthy();
  });

  it.each([" ", "   ", "\t", " \n\t "])(
    "reports a username error for a whitespace-only username %j — DoD-1",
    (username) => {
      const errors = createAdminClientErrors(makeDraft({ username, password: PASSWORD, confirmation: PASSWORD }));
      expect(errors.username).toBeTruthy();
    },
  );

  it("reports a password error for an empty password — DoD-1", () => {
    const errors = createAdminClientErrors(makeDraft({ username: USERNAME, password: "", confirmation: "" }));
    expect(errors.password).toBeTruthy();
  });

  it.each([" ", "    ", "\t", " \n "])(
    "reports a password error for a whitespace-only password %j — DoD-1",
    (password) => {
      const errors = createAdminClientErrors(makeDraft({ username: USERNAME, password, confirmation: password }));
      expect(errors.password).toBeTruthy();
    },
  );

  it.each<[string, string]>([
    ["a different string", `${PASSWORD}x`],
    ["an empty confirmation", ""],
    ["a case-different confirmation", PASSWORD.toUpperCase()],
    ["a confirmation with extra whitespace", ` ${PASSWORD}`],
  ])("reports a confirmation error for %s — DoD-1", (_name, confirmation) => {
    const errors = createAdminClientErrors(makeDraft({ username: USERNAME, password: PASSWORD, confirmation }));
    expect(errors.confirmation).toBeTruthy();
  });

  it("a mismatched confirmation reports only the confirmation — DoD-1", () => {
    const errors = createAdminClientErrors(
      makeDraft({ username: USERNAME, password: PASSWORD, confirmation: "something-else" }),
    );
    expect(Object.keys(errors)).toEqual(["confirmation"]);
  });

  it("imposes no password policy: a one-character matching password is valid — DoD-1 (D16)", () => {
    expect(createAdminClientErrors(makeDraft({ username: "a", password: "x", confirmation: "x" }))).toEqual({});
  });

  it("a username with surrounding whitespace but content is not an error — DoD-1", () => {
    const errors = createAdminClientErrors(
      makeDraft({ username: `  ${USERNAME}  `, password: PASSWORD, confirmation: PASSWORD }),
    );
    expect(errors.username).toBeUndefined();
  });

  it("an entirely empty draft reports username and password errors — DoD-1", () => {
    const errors = createAdminClientErrors(new CreateAdminDraft());
    expect(errors.username).toBeTruthy();
    expect(errors.password).toBeTruthy();
  });

  it("is pure — it writes nothing onto the draft — DoD-1", () => {
    const draft = makeDraft({ username: " ", password: PASSWORD, confirmation: "nope" });
    createAdminClientErrors(draft);
    expect(draft.username).toBe(" ");
    expect(draft.password).toBe(PASSWORD);
    expect(draft.confirmation).toBe("nope");
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitting).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("canSubmitCreateAdmin", () => {
  it("is true for a valid draft with no submit in flight — DoD-2", () => {
    expect(canSubmitCreateAdmin(validDraft())).toBe(true);
  });

  it.each<[string, { username: string; password: string; confirmation: string }]>([
    ["an empty username", { username: "", password: PASSWORD, confirmation: PASSWORD }],
    ["a whitespace-only username", { username: "  ", password: PASSWORD, confirmation: PASSWORD }],
    ["an empty password", { username: USERNAME, password: "", confirmation: "" }],
    ["a whitespace-only password", { username: USERNAME, password: "  ", confirmation: "  " }],
    ["a mismatched confirmation", { username: USERNAME, password: PASSWORD, confirmation: "other" }],
    ["an empty draft", { username: "", password: "", confirmation: "" }],
  ])("is false for %s — DoD-2", (_name, fields) => {
    expect(canSubmitCreateAdmin(makeDraft(fields))).toBe(false);
  });

  it("is false for a valid draft while a submit is in flight — DoD-2", () => {
    const draft = validDraft();
    runInAction(() => {
      draft.submitting = true;
    });
    expect(canSubmitCreateAdmin(draft)).toBe(false);
  });

  it("is false for an invalid draft while a submit is in flight — DoD-2", () => {
    const draft = makeDraft({ username: "", password: PASSWORD, confirmation: PASSWORD });
    runInAction(() => {
      draft.submitting = true;
    });
    expect(canSubmitCreateAdmin(draft)).toBe(false);
  });

  it("is pure — it writes nothing onto the draft — DoD-2", () => {
    const draft = validDraft();
    canSubmitCreateAdmin(draft);
    expect(draft.submitting).toBe(false);
    expect(draft.serverErrors).toEqual({});
  });
});

// ---------------------------------------------------------------------------
describe("submitCreateAdmin — the request", () => {
  it("issues exactly one POST /api/bootstrap/create — DoD-4", async () => {
    const fetchMock = stubFetch(created);
    await submitCreateAdmin(validDraft());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0];
    expect(requestPath(input)).toBe("/api/bootstrap/create");
    expect(requestMethod(input, init)).toBe("POST");
  });

  it("the body carries the username and password and nothing else — DoD-4 (US-001.AC-1)", async () => {
    const fetchMock = stubFetch(created);
    await submitCreateAdmin(validDraft());
    const body = requestJson(fetchMock.mock.calls[0][1]);
    expect(body).toEqual({ username: USERNAME, password: PASSWORD });
    const keys = Object.keys(body as Record<string, unknown>);
    expect(keys).not.toContain("confirmation");
    expect(keys).not.toContain("role");
    expect(keys).not.toContain("id");
  });

  it("a 201 resolves to the created outcome — DoD-4", async () => {
    stubFetch(created);
    await expect(submitCreateAdmin(validDraft())).resolves.toBe("created");
  });

  it("the created path leaves no server error and no submit in flight — DoD-4", async () => {
    stubFetch(created);
    const draft = validDraft();
    await submitCreateAdmin(draft);
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitting).toBe(false);
  });

  it("the in-flight flag is raised while the request is pending — DoD-2", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const draft = validDraft();
    const outcome = submitCreateAdmin(draft);
    await flushMicrotasks();
    expect(draft.submitting).toBe(true);
    expect(canSubmitCreateAdmin(draft)).toBe(false);
    pending.resolve(await created());
    await outcome;
    expect(draft.submitting).toBe(false);
    expect(canSubmitCreateAdmin(draft)).toBe(true);
  });

  it("performs no navigation of its own on success — DoD-5", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(created);
    await submitCreateAdmin(validDraft());
    expect(assignSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("submitCreateAdmin — the refusal", () => {
  it("already_configured resolves to the refused outcome — DoD-6", async () => {
    stubFetch(alreadyConfigured);
    await expect(submitCreateAdmin(validDraft())).resolves.toBe("refused");
  });

  it("the refusal is not written onto the draft as an error — DoD-6", async () => {
    stubFetch(alreadyConfigured);
    const draft = validDraft();
    await submitCreateAdmin(draft);
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitting).toBe(false);
  });

  it("the refusal is recognised by code: a 409 with another code is a failure, not a refusal — DoD-6", async () => {
    stubFetch(envelope("some_other_conflict", "Conflict of another kind.", 409));
    await expect(submitCreateAdmin(validDraft())).resolves.toBe("failed");
  });

  it("performs no navigation on the refusal — DoD-6", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(alreadyConfigured);
    await submitCreateAdmin(validDraft());
    expect(assignSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("submitCreateAdmin — other failures", () => {
  it.each<[string, () => Promise<Response>]>([
    ["a backend error envelope (500)", envelope("internal_error", "Creation exploded zq-42.", 500)],
    ["a transport failure", transportFailure],
    [
      "FastAPI's own 422 body (not the envelope)",
      () =>
        Promise.resolve(
          jsonResponse(
            { detail: [{ type: "string_too_short", loc: ["body", "username"], msg: "too short", input: "" }] },
            422,
          ),
        ),
    ],
  ])("%s resolves to failed and lands on the general key — DoD-7", async (_name, handler) => {
    stubFetch(handler);
    const draft = validDraft();
    await expect(submitCreateAdmin(draft)).resolves.toBe("failed");
    expect(typeof draft.serverErrors.general).toBe("string");
    expect(draft.serverErrors.general).not.toBe("");
    expect(draft.submitting).toBe(false);
  });

  it("a failure preserves the entered username, password and confirmation — DoD-7", async () => {
    stubFetch(envelope("internal_error", "Creation exploded zq-42.", 500));
    const draft = validDraft();
    await submitCreateAdmin(draft);
    expect(draft.username).toBe(USERNAME);
    expect(draft.password).toBe(PASSWORD);
    expect(draft.confirmation).toBe(PASSWORD);
  });

  it("after a failure the draft may be submitted again — DoD-7", async () => {
    stubFetch(envelope("internal_error", "Creation exploded zq-42.", 500));
    const draft = validDraft();
    await submitCreateAdmin(draft);
    expect(canSubmitCreateAdmin(draft)).toBe(true);
  });

  it("the general error does not contain the password — DoD-8", async () => {
    stubFetch(envelope("internal_error", "Creation exploded zq-42.", 500));
    const draft = validDraft();
    await submitCreateAdmin(draft);
    expect(draft.serverErrors.general ?? "").not.toContain(PASSWORD);
  });
});

// ---------------------------------------------------------------------------
describe("submitCreateAdmin — abort", () => {
  it("a pre-aborted signal resolves failed and writes no error onto the draft — DoD-9", async () => {
    stubFetch(abortableNeverAnswers);
    const controller = new AbortController();
    controller.abort();
    const draft = validDraft();
    await expect(submitCreateAdmin(draft, controller.signal)).resolves.toBe("failed");
    expect(draft.serverErrors).toEqual({});
    expect(draft.username).toBe(USERNAME);
    expect(draft.password).toBe(PASSWORD);
    expect(draft.confirmation).toBe(PASSWORD);
  });

  it("aborting mid-flight resolves failed and writes no error onto the draft — DoD-9", async () => {
    stubFetch(abortableNeverAnswers);
    const controller = new AbortController();
    const draft = validDraft();
    const outcome = submitCreateAdmin(draft, controller.signal);
    await flushMicrotasks();
    controller.abort();
    await expect(outcome).resolves.toBe("failed");
    expect(draft.serverErrors).toEqual({});
  });

  it("a failure response arriving after the abort writes no error onto the draft — DoD-9", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const controller = new AbortController();
    const draft = validDraft();
    const outcome = submitCreateAdmin(draft, controller.signal);
    await flushMicrotasks();
    controller.abort();
    pending.resolve(jsonResponse({ error: { code: "internal_error", message: "late zq-9", detail: {} } }, 500));
    await expect(outcome).resolves.toBe("failed");
    expect(draft.serverErrors).toEqual({});
  });
});

// ---------------------------------------------------------------------------
describe("no notification and a pure data class", () => {
  it.each<[string, () => Promise<Response>]>([
    ["created", created],
    ["refused", alreadyConfigured],
    ["a backend failure", envelope("internal_error", "Creation exploded zq-42.", 500)],
    ["a transport failure", transportFailure],
  ])("submitting (%s) calls notifyFailure nowhere — DoD-10", async (_name, handler) => {
    stubFetch(handler);
    await submitCreateAdmin(validDraft());
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("an aborted submit calls notifyFailure nowhere — DoD-10", async () => {
    stubFetch(abortableNeverAnswers);
    const controller = new AbortController();
    controller.abort();
    await submitCreateAdmin(validDraft(), controller.signal);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("the draft class prototype carries no method and no getter — DoD-10", () => {
    expect(Object.getOwnPropertyNames(CreateAdminDraft.prototype)).toEqual(["constructor"]);
  });

  it("a fresh draft holds the five documented fields, each observable and none computed — DoD-10", () => {
    const draft = new CreateAdminDraft();
    for (const name of DRAFT_FIELDS) {
      expect(isObservableProp(draft, name), `field ${name}`).toBe(true);
      expect(isComputedProp(draft, name), `field ${name}`).toBe(false);
    }
  });

  it("a fresh draft starts empty with no server error and no submit in flight — DoD-10", () => {
    const draft = new CreateAdminDraft();
    expect(draft.username).toBe("");
    expect(draft.password).toBe("");
    expect(draft.confirmation).toBe("");
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitting).toBe(false);
  });

  it("no own property of a draft is a function or a computed value — DoD-10", () => {
    const draft = new CreateAdminDraft();
    for (const name of Object.getOwnPropertyNames(draft)) {
      const descriptor = Object.getOwnPropertyDescriptor(draft, name);
      const value = descriptor && "value" in descriptor ? descriptor.value : undefined;
      expect(typeof value, `own property ${name}`).not.toBe("function");
      expect(isComputedProp(draft, name), `own property ${name}`).toBe(false);
    }
  });
});
