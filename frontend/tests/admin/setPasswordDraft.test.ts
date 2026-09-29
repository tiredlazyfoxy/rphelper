// Feature 005, step 008 — the set-password draft, its pure derivations and its effectful submit
// (DoD-1, DoD-3, DoD-4, DoD-10, DoD-13 at the draft level). The modal and its wiring into the
// Users page are in SetPasswordModal.test.tsx.
//
// Expected values come from the step's Interface intent and Definition of done, 008.context.md
// and context.md (D6 no current password / no policy, D16 MobX data class + free functions).
// `fetch` is stubbed per test; `notifyFailure` is mocked at file level.
import { autorun, configure, isComputedProp, isObservableProp, runInAction } from "mobx";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import {
  SetPasswordDraft,
  canSubmitSetPassword,
  setPasswordClientErrors,
  setPasswordErrors,
  submitSetPassword,
} from "../../src/admin/setPasswordDraft";
import type { AdminUserRow } from "../../src/admin/usersPageState";
import { documentNavigation } from "../../src/shared/api";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Fields = { password?: string; confirmation?: string };

const TARGET_ID = "7340032000000101";
const BIG_ID = "9007199254740993"; // 2^53 + 1
const PASSWORD = "Tq!9-new-horse";
const DRAFT_FIELDS = ["password", "confirmation", "serverErrors", "submitStatus"] as const;

beforeAll(() => {
  // MobX 6's default: writing an *observed* observable outside an action warns.
  configure({ enforceActions: "observed" });
});

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

function envelope(code: string, message: string, status: number) {
  return () => Promise.resolve(jsonResponse({ error: { code, message, detail: {} } }, status));
}

function accountRow(overrides: Partial<AdminUserRow> = {}): AdminUserRow {
  return {
    id: TARGET_ID,
    username: "mireille",
    role: "roleplayer",
    is_enabled: true,
    last_login_at: null,
    ...overrides,
  };
}

function ok(row: AdminUserRow = accountRow()) {
  return () => Promise.resolve(jsonResponse(row, 200));
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

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

function makeDraft(fields: Fields = {}): SetPasswordDraft {
  const draft = new SetPasswordDraft();
  runInAction(() => {
    draft.password = fields.password ?? "";
    draft.confirmation = fields.confirmation ?? "";
  });
  return draft;
}

function validDraft(fields: Fields = {}): SetPasswordDraft {
  return makeDraft({ password: PASSWORD, confirmation: PASSWORD, ...fields });
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
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

function snapshot(draft: SetPasswordDraft) {
  return { password: draft.password, confirmation: draft.confirmation };
}

function mobxWarnings(calls: unknown[][]): unknown[][] {
  return calls.filter((call) => call.some((arg) => String(arg).includes("[MobX]")));
}

// ---------------------------------------------------------------------------
describe("setPasswordClientErrors", () => {
  it("reports nothing for a filled, matching draft — DoD-1", () => {
    expect(setPasswordClientErrors(validDraft())).toEqual({});
  });

  it("reports a missing new password — DoD-1", () => {
    const errors = setPasswordClientErrors(makeDraft({ password: "", confirmation: "" }));
    expect(errors.password).toBeTruthy();
  });

  it("a fresh, empty draft reports the missing new password — DoD-1", () => {
    expect(setPasswordClientErrors(new SetPasswordDraft()).password).toBeTruthy();
  });

  it.each<[string, string]>([
    ["a different string", `${PASSWORD}x`],
    ["an empty confirmation", ""],
    ["a case-different confirmation", PASSWORD.toUpperCase()],
    ["a confirmation with extra whitespace", ` ${PASSWORD}`],
  ])("reports a confirmation that does not match: %s — DoD-1", (_name, confirmation) => {
    expect(setPasswordClientErrors(validDraft({ confirmation })).confirmation).toBeTruthy();
  });

  it("a mismatched confirmation reports only the confirmation — DoD-1", () => {
    const errors = setPasswordClientErrors(validDraft({ confirmation: "something-else" }));
    expect(Object.keys(errors)).toEqual(["confirmation"]);
  });

  it("reports only the two client fields — there is no current-password rule — DoD-1 (D6)", () => {
    const errors = setPasswordClientErrors(makeDraft({ password: "", confirmation: "zz" }));
    for (const key of Object.keys(errors)) {
      expect(["password", "confirmation"], key).toContain(key);
    }
  });

  it("needs no network and writes nothing onto the draft — DoD-1", () => {
    const fetchMock = stubFetch(ok());
    const draft = makeDraft({ password: PASSWORD, confirmation: "nope" });
    const before = snapshot(draft);
    setPasswordClientErrors(draft);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(snapshot(draft)).toEqual(before);
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitStatus).toBe("idle");
  });
});

// ---------------------------------------------------------------------------
describe("no password policy beyond non-empty", () => {
  it.each(["x", "1", "!", "aaaaaaaa", "password", "abc", "12345678"])(
    "a new password of %j with a matching confirmation is valid — DoD-1 (D6)",
    (password) => {
      expect(setPasswordClientErrors(validDraft({ password, confirmation: password }))).toEqual({});
    },
  );

  it("a one-character password may be submitted — DoD-1 (D6)", () => {
    expect(canSubmitSetPassword(validDraft({ password: "x", confirmation: "x" }))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("canSubmitSetPassword", () => {
  it("is true for a filled, matching draft — DoD-1, DoD-10", () => {
    expect(canSubmitSetPassword(validDraft())).toBe(true);
  });

  it.each<[string, Fields]>([
    ["an empty new password", { password: "", confirmation: "" }],
    ["a mismatched confirmation", { confirmation: "other" }],
  ])("is false for %s — DoD-1, DoD-10", (_name, fields) => {
    expect(canSubmitSetPassword(validDraft(fields))).toBe(false);
  });

  it("is false for a fresh, empty draft — DoD-1", () => {
    expect(canSubmitSetPassword(new SetPasswordDraft())).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("the draft is a data class; derivations and effects are free functions", () => {
  it("the draft class prototype carries no method and no getter — DoD-10", () => {
    expect(Object.getOwnPropertyNames(SetPasswordDraft.prototype)).toEqual(["constructor"]);
  });

  it("a fresh draft holds exactly its four fields — no current password, no target id — each observable, none computed — DoD-10, DoD-1 (D6)", () => {
    const draft = new SetPasswordDraft();
    expect(Object.getOwnPropertyNames(draft).sort()).toEqual([...DRAFT_FIELDS].sort());
    for (const name of DRAFT_FIELDS) {
      expect(isObservableProp(draft, name), `field ${name}`).toBe(true);
      expect(isComputedProp(draft, name), `field ${name}`).toBe(false);
    }
  });

  it("no own property of a draft is a function or a computed value — DoD-10", () => {
    const draft = new SetPasswordDraft();
    for (const name of Object.getOwnPropertyNames(draft)) {
      const descriptor = Object.getOwnPropertyDescriptor(draft, name);
      const value = descriptor && "value" in descriptor ? descriptor.value : undefined;
      expect(typeof value, `own property ${name}`).not.toBe("function");
      expect(isComputedProp(draft, name), `own property ${name}`).toBe(false);
    }
  });

  it("a fresh draft is empty, idle and carries no server error — DoD-10", () => {
    const draft = new SetPasswordDraft();
    expect(draft.password).toBe("");
    expect(draft.confirmation).toBe("");
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitStatus).toBe("idle");
  });

  it("the derivations are detached free functions taking the draft — DoD-10", () => {
    const clientErrors: (d: SetPasswordDraft) => unknown = setPasswordClientErrors;
    const errors: (d: SetPasswordDraft) => unknown = setPasswordErrors;
    const canSubmit: (d: SetPasswordDraft) => unknown = canSubmitSetPassword;
    expect(clientErrors.call(undefined, validDraft())).toEqual({});
    expect(errors.call(undefined, validDraft())).toEqual({});
    expect(canSubmit.call(undefined, validDraft())).toBe(true);
    expect(canSubmit.call(undefined, makeDraft())).toBe(false);
  });

  it("the merged view carries a client error beside a general server error — DoD-10", () => {
    const draft = validDraft({ confirmation: "mismatch" });
    runInAction(() => {
      draft.serverErrors = { general: "Something went wrong zq-7." };
    });
    const errors = setPasswordErrors(draft);
    expect(errors.confirmation).toBeTruthy();
    expect(errors.general).toBe("Something went wrong zq-7.");
  });

  it("the merged view of a valid draft with no server error is empty — DoD-10", () => {
    expect(setPasswordErrors(validDraft())).toEqual({});
  });

  it("the submit writes to the observed draft only inside actions — no MobX strict-mode warning — DoD-10", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const draft = validDraft();
    const dispose = autorun(() => {
      void draft.password;
      void draft.confirmation;
      void draft.submitStatus;
      void JSON.stringify(draft.serverErrors);
    });
    try {
      stubFetch(ok());
      await submitSetPassword(draft, TARGET_ID, vi.fn());
      stubFetch(envelope("internal_error", "boom zq-500", 500));
      await submitSetPassword(draft, TARGET_ID, vi.fn());
    } finally {
      dispose();
    }
    expect(mobxWarnings(warn.mock.calls as unknown[][])).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("submitSetPassword — success", () => {
  it("issues exactly one POST to that account's password route, with no query — DoD-3 (US-010.AC-2)", async () => {
    const fetchMock = stubFetch(ok());
    await submitSetPassword(validDraft(), TARGET_ID, vi.fn());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0];
    expect(requestUrl(input).pathname).toBe(`/api/admin/users/${TARGET_ID}/password`);
    expect(requestUrl(input).search).toBe("");
    expect(requestMethod(input, init)).toBe("POST");
  });

  it("posts the new password exactly as typed, and nothing else — no confirmation, no current password — DoD-3 (D6)", async () => {
    const fetchMock = stubFetch(ok());
    const password = " Pass Word\t";
    await submitSetPassword(validDraft({ password, confirmation: password }), TARGET_ID, vi.fn());
    expect(requestJson(fetchMock.mock.calls[0][1])).toEqual({ password });
  });

  it("the target id goes into the path as the same string, never parsed — DoD-3", async () => {
    const fetchMock = stubFetch(ok(accountRow({ id: BIG_ID })));
    await submitSetPassword(validDraft(), BIG_ID, vi.fn());
    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe(`/api/admin/users/${BIG_ID}/password`);
  });

  it("invokes the saved callback exactly once, with the affected account — DoD-3 (US-010.AC-2)", async () => {
    const row = accountRow({ username: "ZQ-Target" });
    stubFetch(ok(row));
    const onSaved = vi.fn();
    await submitSetPassword(validDraft(), TARGET_ID, onSaved);
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onSaved.mock.calls[0][0]).toEqual(row);
  });

  it("resolves, leaves no server error and raises no notification — DoD-3", async () => {
    stubFetch(ok());
    const draft = validDraft();
    await expect(submitSetPassword(draft, TARGET_ID, vi.fn())).resolves.toBeUndefined();
    expect(draft.serverErrors).toEqual({});
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("submitSetPassword — every failure lands on the general key", () => {
  const FAILURES: Array<[string, () => Promise<Response>]> = [
    ["a 500 envelope", envelope("internal_error", "Reset exploded zq-500.", 500)],
    ["a 404 user_not_found (stale row)", envelope("user_not_found", "That account does not exist.", 404)],
    ["a 403 envelope", envelope("insufficient_role", "You need a higher role zq-403.", 403)],
    ["a 409 envelope", envelope("conflict", "Conflict zq-409.", 409)],
    ["a 400 envelope whose message talks about the password", envelope("bad_request", "Password too weak zq-400.", 400)],
    [
      "FastAPI's own 422 body (not the envelope)",
      () =>
        Promise.resolve(
          jsonResponse({ detail: [{ type: "string_too_short", loc: ["body", "password"], msg: "too short", input: "" }] }, 422),
        ),
    ],
    [
      "a 502 with a malformed (HTML) body",
      () => Promise.resolve(new Response("<html><body>Bad Gateway</body></html>", { status: 502, headers: { "Content-Type": "text/html" } })),
    ],
    ["a transport failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ];

  it.each(FAILURES)("%s lands on the general key and nothing else — DoD-4, DoD-13", async (_name, handler) => {
    stubFetch(handler);
    const draft = validDraft();
    await expect(submitSetPassword(draft, TARGET_ID, vi.fn())).resolves.toBeUndefined();
    expect(typeof draft.serverErrors.general).toBe("string");
    expect(draft.serverErrors.general).not.toBe("");
    expect(Object.keys(draft.serverErrors)).toEqual(["general"]);
    expect(draft.submitStatus).toBe("idle");
  });

  it.each(FAILURES)("%s does not invoke the saved callback and keeps the typed values — DoD-4", async (_name, handler) => {
    stubFetch(handler);
    const onSaved = vi.fn();
    const draft = validDraft();
    const before = snapshot(draft);
    await submitSetPassword(draft, TARGET_ID, onSaved);
    expect(onSaved).not.toHaveBeenCalled();
    expect(snapshot(draft)).toEqual(before);
  });

  it("a 401 lands on the general key too — DoD-4", async () => {
    vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(envelope("not_authenticated", "Sign in again zq-401.", 401));
    const draft = validDraft();
    await submitSetPassword(draft, TARGET_ID, vi.fn());
    expect(Object.keys(draft.serverErrors)).toEqual(["general"]);
  });

  it("no field key is ever produced, whatever the prose says — DoD-4, DoD-13", async () => {
    stubFetch(envelope("bad_request", "The confirmation password does not match zq-400.", 400));
    const draft = validDraft();
    await submitSetPassword(draft, TARGET_ID, vi.fn());
    expect(Object.keys(draft.serverErrors)).toEqual(["general"]);
    const merged = setPasswordErrors(draft);
    expect(merged.password).toBeUndefined();
    expect(merged.confirmation).toBeUndefined();
  });

  it("a failure raises no notification — DoD-4, DoD-13", async () => {
    stubFetch(envelope("internal_error", "Reset exploded zq-500.", 500));
    await submitSetPassword(validDraft(), TARGET_ID, vi.fn());
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("submitSetPassword — abort", () => {
  it("a pre-aborted signal writes nothing and invokes no callback — DoD-10", async () => {
    stubFetch(abortableNeverAnswers);
    const controller = new AbortController();
    controller.abort();
    const onSaved = vi.fn();
    const draft = validDraft();
    const before = snapshot(draft);
    await submitSetPassword(draft, TARGET_ID, onSaved, controller.signal).catch(() => undefined);
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitStatus).toBe("idle");
    expect(snapshot(draft)).toEqual(before);
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("a failure arriving after the abort writes no error and invokes no callback — DoD-10", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const controller = new AbortController();
    const onSaved = vi.fn();
    const draft = validDraft();
    const run = submitSetPassword(draft, TARGET_ID, onSaved, controller.signal);
    await flushMicrotasks();
    controller.abort();
    pending.resolve(jsonResponse({ error: { code: "internal_error", message: "late zq-9", detail: {} } }, 500));
    await run.catch(() => undefined);
    expect(draft.serverErrors).toEqual({});
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("a success arriving after the abort invokes no callback — DoD-10", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const controller = new AbortController();
    const onSaved = vi.fn();
    const run = submitSetPassword(validDraft(), TARGET_ID, onSaved, controller.signal);
    await flushMicrotasks();
    controller.abort();
    pending.resolve(jsonResponse(accountRow(), 200));
    await run.catch(() => undefined);
    expect(onSaved).not.toHaveBeenCalled();
  });
});
