// Feature 005, step 008 — the change-role draft, its pure derivations and its effectful submit
// (DoD-5, DoD-6, DoD-7, DoD-10, DoD-13 at the draft level). The modal and its wiring into the
// Users page are in ChangeRoleModal.test.tsx.
//
// Expected values come from the step's Interface intent and Definition of done, 008.context.md
// and context.md (D1 the self-target refusal is the server's, D16 MobX data class + free
// functions). `fetch` is stubbed per test; `notifyFailure` is mocked at file level.
//
// Recognition convention (from spec wording, for the verifier): the 409 message "an
// administrator cannot change their own role" = matches both OWN_ROLE and CANNOT below.
import { autorun, configure, isComputedProp, isObservableProp, runInAction } from "mobx";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ChangeRoleDraft,
  canSubmitChangeRole,
  changeRoleClientErrors,
  changeRoleErrors,
  submitChangeRole,
} from "../../src/admin/changeRoleDraft";
import type { AdminUserRole, AdminUserRow } from "../../src/admin/usersPageState";
import { documentNavigation } from "../../src/shared/api";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const TARGET_ID = "7340032000000101";
const BIG_ID = "9007199254740993"; // 2^53 + 1
const DRAFT_FIELDS = ["role", "serverErrors", "submitStatus"] as const;
const ROLES: AdminUserRole[] = ["roleplayer", "admin"];
const OWN_ROLE = /\bown\s+role\b/i;
const CANNOT = /cannot|can't|can not|not allowed|may not|not permitted|unable/i;

beforeAll(() => {
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

const selfRefused = envelope("self_role_change_refused", "You cannot change your own role.", 409);

function accountRow(overrides: Partial<AdminUserRow> = {}): AdminUserRow {
  return {
    id: TARGET_ID,
    username: "mireille",
    role: "admin",
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

function draftWith(role: AdminUserRole | null, current: AdminUserRole = "roleplayer"): ChangeRoleDraft {
  const draft = new ChangeRoleDraft(current);
  runInAction(() => {
    draft.role = role;
  });
  return draft;
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

function mobxWarnings(calls: unknown[][]): unknown[][] {
  return calls.filter((call) => call.some((arg) => String(arg).includes("[MobX]")));
}

// ---------------------------------------------------------------------------
describe("the draft initialises from the target's current role", () => {
  it.each(ROLES)("a draft built for a %s account has that role selected — DoD-5", (role) => {
    const draft = new ChangeRoleDraft(role);
    expect(draft.role).toBe(role);
  });

  it("a fresh draft is idle with no server error — DoD-5, DoD-10", () => {
    const draft = new ChangeRoleDraft("admin");
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitStatus).toBe("idle");
  });
});

// ---------------------------------------------------------------------------
describe("the only client rule is that a role is selected", () => {
  it.each(ROLES)("reports nothing when %s is selected — DoD-5", (role) => {
    expect(changeRoleClientErrors(draftWith(role))).toEqual({});
  });

  it("reports the role when none is selected — DoD-5", () => {
    const errors = changeRoleClientErrors(draftWith(null));
    expect(errors.role).toBeTruthy();
    expect(Object.keys(errors)).toEqual(["role"]);
  });

  it.each(ROLES)("permits a submit when %s is selected — DoD-5", (role) => {
    expect(canSubmitChangeRole(draftWith(role))).toBe(true);
  });

  it("does not permit a submit when no role is selected — DoD-5", () => {
    expect(canSubmitChangeRole(draftWith(null))).toBe(false);
  });

  it.each<[AdminUserRole, AdminUserRole]>([
    ["admin", "admin"],
    ["roleplayer", "roleplayer"],
    ["admin", "roleplayer"],
    ["roleplayer", "admin"],
  ])("current %s, selected %s: no client error and submittable — no rule beyond 'selected' — DoD-5 (D1)", (current, selected) => {
    const draft = draftWith(selected, current);
    expect(changeRoleClientErrors(draft)).toEqual({});
    expect(canSubmitChangeRole(draft)).toBe(true);
  });

  it("the derivations need no network and write nothing — DoD-5", () => {
    const fetchMock = stubFetch(ok());
    const draft = draftWith(null);
    changeRoleClientErrors(draft);
    canSubmitChangeRole(draft);
    changeRoleErrors(draft);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(draft.role).toBeNull();
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitStatus).toBe("idle");
  });
});

// ---------------------------------------------------------------------------
describe("no self-target rule of its own", () => {
  it("an administrator-role draft (as one's own row would be) submits to the server, which decides — DoD-5 (D1)", async () => {
    const fetchMock = stubFetch(selfRefused);
    await submitChangeRole(draftWith("roleplayer", "admin"), TARGET_ID, vi.fn());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0];
    expect(requestMethod(input, init)).toBe("POST");
    expect(requestUrl(input).pathname).toBe(`/api/admin/users/${TARGET_ID}/role`);
  });

  it("the submit asks nothing about the caller — its only request is the role route — DoD-5 (D1)", async () => {
    const fetchMock = stubFetch(ok());
    await submitChangeRole(draftWith("admin"), TARGET_ID, vi.fn());
    const paths = fetchMock.mock.calls.map(([input]) => requestUrl(input).pathname);
    expect(paths).toEqual([`/api/admin/users/${TARGET_ID}/role`]);
  });
});

// ---------------------------------------------------------------------------
describe("the draft is a data class; derivations and effects are free functions", () => {
  it("the draft class prototype carries no method and no getter — DoD-10", () => {
    expect(Object.getOwnPropertyNames(ChangeRoleDraft.prototype)).toEqual(["constructor"]);
  });

  it("a fresh draft holds exactly its three fields — no target id — each observable, none computed — DoD-10", () => {
    const draft = new ChangeRoleDraft("roleplayer");
    expect(Object.getOwnPropertyNames(draft).sort()).toEqual([...DRAFT_FIELDS].sort());
    for (const name of DRAFT_FIELDS) {
      expect(isObservableProp(draft, name), `field ${name}`).toBe(true);
      expect(isComputedProp(draft, name), `field ${name}`).toBe(false);
    }
  });

  it("no own property of a draft is a function or a computed value — DoD-10", () => {
    const draft = new ChangeRoleDraft("admin");
    for (const name of Object.getOwnPropertyNames(draft)) {
      const descriptor = Object.getOwnPropertyDescriptor(draft, name);
      const value = descriptor && "value" in descriptor ? descriptor.value : undefined;
      expect(typeof value, `own property ${name}`).not.toBe("function");
      expect(isComputedProp(draft, name), `own property ${name}`).toBe(false);
    }
  });

  it("the derivations are detached free functions taking the draft — DoD-10", () => {
    const clientErrors: (d: ChangeRoleDraft) => unknown = changeRoleClientErrors;
    const errors: (d: ChangeRoleDraft) => unknown = changeRoleErrors;
    const canSubmit: (d: ChangeRoleDraft) => unknown = canSubmitChangeRole;
    expect(clientErrors.call(undefined, draftWith("admin"))).toEqual({});
    expect(errors.call(undefined, draftWith("admin"))).toEqual({});
    expect(canSubmit.call(undefined, draftWith("admin"))).toBe(true);
    expect(canSubmit.call(undefined, draftWith(null))).toBe(false);
  });

  it("the merged view carries the client error beside a general server error — DoD-10", () => {
    const draft = draftWith(null);
    runInAction(() => {
      draft.serverErrors = { general: "Something went wrong zq-7." };
    });
    const errors = changeRoleErrors(draft);
    expect(errors.role).toBeTruthy();
    expect(errors.general).toBe("Something went wrong zq-7.");
  });

  it("the submit writes to the observed draft only inside actions — no MobX strict-mode warning — DoD-10", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const draft = draftWith("admin");
    const dispose = autorun(() => {
      void draft.role;
      void draft.submitStatus;
      void JSON.stringify(draft.serverErrors);
    });
    try {
      stubFetch(ok());
      await submitChangeRole(draft, TARGET_ID, vi.fn());
      stubFetch(selfRefused);
      await submitChangeRole(draft, TARGET_ID, vi.fn());
      stubFetch(envelope("internal_error", "boom zq-500", 500));
      await submitChangeRole(draft, TARGET_ID, vi.fn());
    } finally {
      dispose();
    }
    expect(mobxWarnings(warn.mock.calls as unknown[][])).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("submitChangeRole — success", () => {
  it.each(ROLES)("posts the selected role %s to that account's role route, and nothing else — DoD-6", async (role) => {
    const fetchMock = stubFetch(ok(accountRow({ role })));
    await submitChangeRole(draftWith(role, role === "admin" ? "roleplayer" : "admin"), TARGET_ID, vi.fn());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0];
    expect(requestMethod(input, init)).toBe("POST");
    expect(requestUrl(input).pathname).toBe(`/api/admin/users/${TARGET_ID}/role`);
    expect(requestUrl(input).search).toBe("");
    expect(requestJson(init)).toEqual({ role });
  });

  it("the target id goes into the path as the same string, never parsed — DoD-6", async () => {
    const fetchMock = stubFetch(ok(accountRow({ id: BIG_ID })));
    await submitChangeRole(draftWith("admin"), BIG_ID, vi.fn());
    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe(`/api/admin/users/${BIG_ID}/role`);
  });

  it("invokes the saved callback exactly once, with the affected account — DoD-6", async () => {
    const row = accountRow({ username: "ZQ-Target", role: "admin" });
    stubFetch(ok(row));
    const onSaved = vi.fn();
    await submitChangeRole(draftWith("admin"), TARGET_ID, onSaved);
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onSaved.mock.calls[0][0]).toEqual(row);
  });

  it("resolves, leaves no server error and raises no notification — DoD-6", async () => {
    stubFetch(ok());
    const draft = draftWith("admin");
    await expect(submitChangeRole(draft, TARGET_ID, vi.fn())).resolves.toBeUndefined();
    expect(draft.serverErrors).toEqual({});
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("submitChangeRole — a 409 is the self-target refusal", () => {
  it("a 409 puts an 'administrator cannot change their own role' message on the general key only — DoD-7", async () => {
    stubFetch(selfRefused);
    const draft = draftWith("roleplayer", "admin");
    await expect(submitChangeRole(draft, TARGET_ID, vi.fn())).resolves.toBeUndefined();
    expect(Object.keys(draft.serverErrors)).toEqual(["general"]);
    expect(draft.serverErrors.general).toMatch(OWN_ROLE);
    expect(draft.serverErrors.general).toMatch(CANNOT);
  });

  it("the mapping is by status: a 409 whose prose says something else still yields the own-role message — DoD-7, DoD-13", async () => {
    stubFetch(envelope("self_role_change_refused", "Kettle zq-409 overflowed.", 409));
    const draft = draftWith("roleplayer", "admin");
    await submitChangeRole(draft, TARGET_ID, vi.fn());
    expect(Object.keys(draft.serverErrors)).toEqual(["general"]);
    expect(draft.serverErrors.general).toMatch(OWN_ROLE);
    expect(draft.serverErrors.general).toMatch(CANNOT);
  });

  it("a 409 does not invoke the saved callback, keeps the selection and ends idle — DoD-7", async () => {
    stubFetch(selfRefused);
    const onSaved = vi.fn();
    const draft = draftWith("roleplayer", "admin");
    await submitChangeRole(draft, TARGET_ID, onSaved);
    expect(onSaved).not.toHaveBeenCalled();
    expect(draft.role).toBe("roleplayer");
    expect(draft.submitStatus).toBe("idle");
  });

  it("a 409 shows through the merged view on the general key — DoD-7", async () => {
    stubFetch(selfRefused);
    const draft = draftWith("roleplayer", "admin");
    await submitChangeRole(draft, TARGET_ID, vi.fn());
    expect(changeRoleErrors(draft).general).toMatch(OWN_ROLE);
    expect(changeRoleErrors(draft).role).toBeUndefined();
  });

  it("a 409 raises no notification — DoD-7, DoD-13", async () => {
    stubFetch(selfRefused);
    await submitChangeRole(draftWith("roleplayer", "admin"), TARGET_ID, vi.fn());
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("submitChangeRole — every other failure lands on the general key too", () => {
  const FAILURES: Array<[string, () => Promise<Response>]> = [
    ["a 500 envelope", envelope("internal_error", "Role change exploded zq-500.", 500)],
    ["a 404 user_not_found (stale row)", envelope("user_not_found", "That account does not exist.", 404)],
    ["a 403 envelope", envelope("insufficient_role", "You need a higher role zq-403.", 403)],
    ["a 400 envelope whose message talks about the role", envelope("bad_request", "Role is invalid zq-400.", 400)],
    [
      "FastAPI's own 422 body",
      () => Promise.resolve(jsonResponse({ detail: [{ type: "enum", loc: ["body", "role"], msg: "bad", input: "x" }] }, 422)),
    ],
    [
      "a 502 with a malformed (HTML) body",
      () => Promise.resolve(new Response("<html><body>Bad Gateway</body></html>", { status: 502, headers: { "Content-Type": "text/html" } })),
    ],
    ["a transport failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ];

  it.each(FAILURES)("%s lands on the general key and nothing else — DoD-7, DoD-13", async (_name, handler) => {
    stubFetch(handler);
    const draft = draftWith("admin");
    await expect(submitChangeRole(draft, TARGET_ID, vi.fn())).resolves.toBeUndefined();
    expect(typeof draft.serverErrors.general).toBe("string");
    expect(draft.serverErrors.general).not.toBe("");
    expect(Object.keys(draft.serverErrors)).toEqual(["general"]);
    expect(draft.submitStatus).toBe("idle");
  });

  it.each(FAILURES)("%s does not invoke the saved callback and keeps the selection — DoD-7", async (_name, handler) => {
    stubFetch(handler);
    const onSaved = vi.fn();
    const draft = draftWith("admin");
    await submitChangeRole(draft, TARGET_ID, onSaved);
    expect(onSaved).not.toHaveBeenCalled();
    expect(draft.role).toBe("admin");
  });

  it("a 401 lands on the general key too — DoD-7", async () => {
    vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(envelope("not_authenticated", "Sign in again zq-401.", 401));
    const draft = draftWith("admin");
    await submitChangeRole(draft, TARGET_ID, vi.fn());
    expect(Object.keys(draft.serverErrors)).toEqual(["general"]);
  });
});

// ---------------------------------------------------------------------------
describe("submitChangeRole — abort", () => {
  it("a pre-aborted signal writes nothing and invokes no callback — DoD-10", async () => {
    stubFetch(abortableNeverAnswers);
    const controller = new AbortController();
    controller.abort();
    const onSaved = vi.fn();
    const draft = draftWith("admin");
    await submitChangeRole(draft, TARGET_ID, onSaved, controller.signal).catch(() => undefined);
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitStatus).toBe("idle");
    expect(draft.role).toBe("admin");
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("a 409 arriving after the abort writes no error and invokes no callback — DoD-10", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const controller = new AbortController();
    const onSaved = vi.fn();
    const draft = draftWith("roleplayer", "admin");
    const run = submitChangeRole(draft, TARGET_ID, onSaved, controller.signal);
    await flushMicrotasks();
    controller.abort();
    pending.resolve(jsonResponse({ error: { code: "self_role_change_refused", message: "late zq-9", detail: {} } }, 409));
    await run.catch(() => undefined);
    expect(draft.serverErrors).toEqual({});
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("a success arriving after the abort invokes no callback — DoD-10", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const controller = new AbortController();
    const onSaved = vi.fn();
    const run = submitChangeRole(draftWith("admin"), TARGET_ID, onSaved, controller.signal);
    await flushMicrotasks();
    controller.abort();
    pending.resolve(jsonResponse(accountRow(), 200));
    await run.catch(() => undefined);
    expect(onSaved).not.toHaveBeenCalled();
  });
});
