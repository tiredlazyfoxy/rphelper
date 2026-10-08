// Feature 005, step 007 — the create-account draft, its pure derivations and its effectful
// submit (DoD-1..DoD-7, DoD-8 default role, DoD-11 no open flag, DoD-12 ids are strings).
// The modal, the page's Create button and the re-load are in CreateUserModal.test.tsx.
//
// Expected values come from the step's Interface intent and Definition of done, 007.context.md
// and context.md (D6 no password policy, D10 by-status mapping, D16 MobX data class + free
// functions). `fetch` is stubbed per test; `notifyFailure` is mocked at file level.
import { readFileSync } from "node:fs";
import path from "node:path";
import { isComputedProp, isObservableProp, runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CreateUserDraft,
  canSubmitCreateUser,
  createUserClientErrors,
  createUserErrors,
  submitCreateUser,
} from "../../src/admin/createUserDraft";
import type { AdminUserRow } from "../../src/admin/usersPageState";
import { documentNavigation } from "../../src/shared/api";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Fields = { username?: string; password?: string; confirmation?: string; role?: "roleplayer" | "admin" };

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const DRAFT_MODULE = path.join(FRONTEND_ROOT, "src", "admin", "createUserDraft.ts");

const CREATE_PATH = "/api/admin/users";
const USERNAME = "mireille";
const PASSWORD = "Tq!9-correct-horse";
const BIG_ID = "9007199254740993"; // 2^53 + 1
const DRAFT_FIELDS = ["username", "password", "confirmation", "role", "serverErrors", "submitStatus"] as const;
/** A "username taken" message (admin-surfaces.md's create-modal mapping). */
const USERNAME_TAKEN = /taken|already|in use|exists|unavailable/i;

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

function createdRow(overrides: Partial<AdminUserRow> = {}): AdminUserRow {
  return {
    id: "7340032000000201",
    username: USERNAME,
    role: "roleplayer",
    is_enabled: true,
    last_login_at: null,
    ...overrides,
  };
}

function created(row: AdminUserRow = createdRow()) {
  return () => Promise.resolve(jsonResponse(row, 201));
}

const usernameTaken = envelope("username_taken", "That username is already taken.", 409);

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

function makeDraft(fields: Fields = {}): CreateUserDraft {
  const draft = new CreateUserDraft();
  runInAction(() => {
    draft.username = fields.username ?? "";
    draft.password = fields.password ?? "";
    draft.confirmation = fields.confirmation ?? "";
    if (fields.role !== undefined) draft.role = fields.role;
  });
  return draft;
}

function validDraft(fields: Fields = {}): CreateUserDraft {
  return makeDraft({ username: USERNAME, password: PASSWORD, confirmation: PASSWORD, ...fields });
}

function requestPath(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost").pathname;
}

function requestSearch(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost").search;
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

function snapshot(draft: CreateUserDraft) {
  return {
    username: draft.username,
    password: draft.password,
    confirmation: draft.confirmation,
    role: draft.role,
  };
}

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

// ---------------------------------------------------------------------------
describe("createUserClientErrors", () => {
  it("reports nothing for a filled, matching draft — DoD-1", () => {
    expect(createUserClientErrors(validDraft())).toEqual({});
  });

  it("reports nothing for a filled, matching draft with the admin role — DoD-1", () => {
    expect(createUserClientErrors(validDraft({ role: "admin" }))).toEqual({});
  });

  it("reports a missing username — DoD-1", () => {
    const errors = createUserClientErrors(validDraft({ username: "" }));
    expect(errors.username).toBeTruthy();
    expect(Object.keys(errors)).toEqual(["username"]);
  });

  it.each([" ", "   ", "\t", " \n\t "])("a whitespace-only username %j counts as missing — DoD-1", (username) => {
    expect(createUserClientErrors(validDraft({ username })).username).toBeTruthy();
  });

  it("reports a missing password — DoD-1", () => {
    const errors = createUserClientErrors(validDraft({ password: "", confirmation: "" }));
    expect(errors.password).toBeTruthy();
  });

  it.each([" ", "    ", "\t", " \n "])("a whitespace-only password %j counts as missing — DoD-1", (password) => {
    const errors = createUserClientErrors(validDraft({ password, confirmation: password }));
    expect(errors.password).toBeTruthy();
  });

  it.each<[string, string]>([
    ["a different string", `${PASSWORD}x`],
    ["an empty confirmation", ""],
    ["a case-different confirmation", PASSWORD.toUpperCase()],
    ["a confirmation with extra whitespace", ` ${PASSWORD}`],
  ])("reports a confirmation that does not match: %s — DoD-1", (_name, confirmation) => {
    expect(createUserClientErrors(validDraft({ confirmation })).confirmation).toBeTruthy();
  });

  it("a mismatched confirmation reports only the confirmation — DoD-1", () => {
    const errors = createUserClientErrors(validDraft({ confirmation: "something-else" }));
    expect(Object.keys(errors)).toEqual(["confirmation"]);
  });

  it("an entirely empty draft reports a missing username and a missing password — DoD-1", () => {
    const errors = createUserClientErrors(new CreateUserDraft());
    expect(errors.username).toBeTruthy();
    expect(errors.password).toBeTruthy();
  });

  it("a username with surrounding whitespace but content is filled — DoD-1", () => {
    expect(createUserClientErrors(validDraft({ username: `  ${USERNAME}  ` })).username).toBeUndefined();
  });

  it("needs no render and no network, and writes nothing onto the draft — DoD-1", () => {
    const fetchMock = stubFetch(created());
    const draft = makeDraft({ username: " ", password: PASSWORD, confirmation: "nope" });
    const before = snapshot(draft);
    createUserClientErrors(draft);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(snapshot(draft)).toEqual(before);
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitStatus).toBe("idle");
  });
});

// ---------------------------------------------------------------------------
describe("no password policy", () => {
  it.each(["x", "1", "!", "aaaaaaaa", "password"])(
    "a password of %j with a matching confirmation is valid client-side — DoD-2 (D6)",
    (password) => {
      expect(createUserClientErrors(validDraft({ password, confirmation: password }))).toEqual({});
    },
  );

  it("a one-character password may be submitted — DoD-2 (D6)", () => {
    expect(canSubmitCreateUser(validDraft({ username: "a", password: "x", confirmation: "x" }))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("canSubmitCreateUser", () => {
  it("is true for a valid draft with no submit in flight — DoD-3", () => {
    expect(canSubmitCreateUser(validDraft())).toBe(true);
  });

  it.each<[string, Fields]>([
    ["an empty username", { username: "" }],
    ["a whitespace-only username", { username: "  " }],
    ["an empty password", { password: "", confirmation: "" }],
    ["a whitespace-only password", { password: "  ", confirmation: "  " }],
    ["a mismatched confirmation", { confirmation: "other" }],
  ])("is false for %s — DoD-3", (_name, fields) => {
    expect(canSubmitCreateUser(validDraft(fields))).toBe(false);
  });

  it("is false for a fresh, empty draft — DoD-3", () => {
    expect(canSubmitCreateUser(new CreateUserDraft())).toBe(false);
  });

  it("is false for a valid draft while a submit is in flight — DoD-3", () => {
    const draft = validDraft();
    runInAction(() => {
      draft.submitStatus = "submitting";
    });
    expect(canSubmitCreateUser(draft)).toBe(false);
  });

  it("is false for an invalid draft while a submit is in flight — DoD-3", () => {
    const draft = validDraft({ username: "" });
    runInAction(() => {
      draft.submitStatus = "submitting";
    });
    expect(canSubmitCreateUser(draft)).toBe(false);
  });

  it("is false while a real submit is pending, and true again once it has failed — DoD-3", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const draft = validDraft();
    const run = submitCreateUser(draft, vi.fn());
    await flushMicrotasks();
    expect(draft.submitStatus).toBe("submitting");
    expect(canSubmitCreateUser(draft)).toBe(false);

    pending.resolve(jsonResponse({ error: { code: "internal_error", message: "boom zq-1", detail: {} } }, 500));
    await run;
    expect(draft.submitStatus).toBe("idle");
    expect(canSubmitCreateUser(draft)).toBe(true);
  });

  it("is pure — it writes nothing onto the draft — DoD-3", () => {
    const draft = validDraft();
    canSubmitCreateUser(draft);
    expect(draft.submitStatus).toBe("idle");
    expect(draft.serverErrors).toEqual({});
  });
});

// ---------------------------------------------------------------------------
describe("the draft is a data class; derivations are free functions", () => {
  it("the draft class prototype carries no method and no getter — DoD-4", () => {
    expect(Object.getOwnPropertyNames(CreateUserDraft.prototype)).toEqual(["constructor"]);
  });

  it("a fresh draft holds exactly the six documented fields, each observable and none computed — DoD-4, DoD-11", () => {
    const draft = new CreateUserDraft();
    expect(Object.getOwnPropertyNames(draft).sort()).toEqual([...DRAFT_FIELDS].sort());
    for (const name of DRAFT_FIELDS) {
      expect(isObservableProp(draft, name), `field ${name}`).toBe(true);
      expect(isComputedProp(draft, name), `field ${name}`).toBe(false);
    }
  });

  it("no own property of a draft is a function or a computed value — DoD-4", () => {
    const draft = new CreateUserDraft();
    for (const name of Object.getOwnPropertyNames(draft)) {
      const descriptor = Object.getOwnPropertyDescriptor(draft, name);
      const value = descriptor && "value" in descriptor ? descriptor.value : undefined;
      expect(typeof value, `own property ${name}`).not.toBe("function");
      expect(isComputedProp(draft, name), `own property ${name}`).toBe(false);
    }
  });

  it("the draft carries no open flag — the modal's open state is not its field — DoD-11", () => {
    const draft = new CreateUserDraft();
    const names = Object.getOwnPropertyNames(draft);
    expect(names.filter((name) => /open|visible|shown/i.test(name))).toEqual([]);
  });

  it("a fresh draft is empty, idle, with no server error and the lower rung chosen — DoD-4, DoD-8", () => {
    const draft = new CreateUserDraft();
    expect(draft.username).toBe("");
    expect(draft.password).toBe("");
    expect(draft.confirmation).toBe("");
    expect(draft.role).toBe("roleplayer");
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitStatus).toBe("idle");
  });

  it("the derivations are detached free functions taking the draft — DoD-4", () => {
    const clientErrors: (d: CreateUserDraft) => unknown = createUserClientErrors;
    const errors: (d: CreateUserDraft) => unknown = createUserErrors;
    const canSubmit: (d: CreateUserDraft) => unknown = canSubmitCreateUser;
    const draft = validDraft();
    expect(clientErrors.call(undefined, draft)).toEqual({});
    expect(errors.call(undefined, draft)).toEqual({});
    expect(canSubmit.call(undefined, draft)).toBe(true);
    expect(canSubmit.call(undefined, makeDraft())).toBe(false);
  });

  it("the merged view carries a client error beside a general server error — DoD-4", () => {
    const draft = validDraft({ password: "", confirmation: "" });
    runInAction(() => {
      draft.serverErrors = { general: "Something went wrong zq-7." };
    });
    const errors = createUserErrors(draft);
    expect(errors.password).toBeTruthy();
    expect(errors.general).toBe("Something went wrong zq-7.");
  });

  it("the merged view carries a server username error on an otherwise valid draft — DoD-4", () => {
    const draft = validDraft();
    runInAction(() => {
      draft.serverErrors = { username: "That username is taken zq-8." };
    });
    const errors = createUserErrors(draft);
    expect(errors.username).toBe("That username is taken zq-8.");
    expect(errors.general).toBeUndefined();
    expect(errors.password).toBeUndefined();
    expect(errors.confirmation).toBeUndefined();
  });

  it("the merged view of a valid draft with no server error is empty — DoD-4", () => {
    expect(createUserErrors(validDraft())).toEqual({});
  });

  it("the merged view carries every client error of an invalid draft — DoD-4", () => {
    const draft = makeDraft({ username: "", password: "", confirmation: "zz" });
    const client = createUserClientErrors(draft);
    const merged = createUserErrors(draft);
    for (const key of Object.keys(client) as Array<keyof typeof client>) {
      expect(merged[key], key).toBe(client[key]);
    }
  });
});

// ---------------------------------------------------------------------------
describe("submitCreateUser — success", () => {
  it("issues exactly one POST /api/admin/users with no query — DoD-5 (US-008.AC-1)", async () => {
    const fetchMock = stubFetch(created());
    await submitCreateUser(validDraft(), vi.fn());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0];
    expect(requestPath(input)).toBe(CREATE_PATH);
    expect(requestSearch(input)).toBe("");
    expect(requestMethod(input, init)).toBe("POST");
  });

  it("posts the username, password and role exactly as typed — no trimming, no case folding — DoD-5", async () => {
    const fetchMock = stubFetch(created());
    const username = "  Mireille Of The Lake ";
    const password = " Pass Word\t";
    await submitCreateUser(validDraft({ username, password, confirmation: password, role: "admin" }), vi.fn());
    expect(requestJson(fetchMock.mock.calls[0][1])).toEqual({ username, password, role: "admin" });
  });

  it("posts the default role when none was chosen, and never the confirmation — DoD-5", async () => {
    const fetchMock = stubFetch(created());
    await submitCreateUser(validDraft(), vi.fn());
    const body = requestJson(fetchMock.mock.calls[0][1]) as Record<string, unknown>;
    expect(body).toEqual({ username: USERNAME, password: PASSWORD, role: "roleplayer" });
    expect(Object.keys(body).sort()).toEqual(["password", "role", "username"]);
  });

  it("invokes the saved callback exactly once, with the created account — DoD-5 (US-008.AC-1)", async () => {
    const row = createdRow({ username: "ZQ-Newcomer" });
    stubFetch(created(row));
    const onSaved = vi.fn();
    await submitCreateUser(validDraft({ username: "ZQ-Newcomer" }), onSaved);
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onSaved.mock.calls[0][0]).toEqual(row);
  });

  it("leaves no server error, the typed values untouched, and no notification — DoD-5", async () => {
    stubFetch(created());
    const draft = validDraft();
    const before = snapshot(draft);
    await expect(submitCreateUser(draft, vi.fn())).resolves.toBeUndefined();
    expect(draft.serverErrors).toEqual({});
    expect(snapshot(draft)).toEqual(before);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("the created account's id reaches the callback as the same string, never parsed — DoD-12", async () => {
    stubFetch(created(createdRow({ id: BIG_ID })));
    const onSaved = vi.fn();
    await submitCreateUser(validDraft(), onSaved);
    const passed = onSaved.mock.calls[0][0] as AdminUserRow;
    expect(passed.id).toBe(BIG_ID);
    expect(typeof passed.id).toBe("string");
  });

  it("the draft module uses no parseInt and types no id as a number — DoD-12", () => {
    const source = stripComments(readFileSync(DRAFT_MODULE, "utf8"));
    expect(source).not.toMatch(/\bparseInt\b|\bparseFloat\b|\bBigInt\s*\(/);
    expect(source).not.toMatch(/\b\w*(?:id|Id)\s*\??\s*:\s*number\b/);
  });
});

// ---------------------------------------------------------------------------
describe("submitCreateUser — a 409 lands on the username field", () => {
  it("a 409 username_taken puts a 'username taken' message on the username key and nothing on general — DoD-6", async () => {
    stubFetch(usernameTaken);
    const draft = validDraft();
    await expect(submitCreateUser(draft, vi.fn())).resolves.toBeUndefined();
    expect(draft.serverErrors.username).toMatch(USERNAME_TAKEN);
    expect(draft.serverErrors.general).toBeUndefined();
    expect(Object.keys(draft.serverErrors)).toEqual(["username"]);
  });

  it("the 409 mapping is by status: a 409 whose message says nothing about usernames still lands on username — DoD-6, DoD-7", async () => {
    stubFetch(envelope("username_taken", "Kettle zq-409 overflowed.", 409));
    const draft = validDraft();
    await submitCreateUser(draft, vi.fn());
    expect(draft.serverErrors.username).toMatch(USERNAME_TAKEN);
    expect(draft.serverErrors.general).toBeUndefined();
  });

  it("a 409 does not invoke the saved callback and keeps every typed value — DoD-6", async () => {
    stubFetch(usernameTaken);
    const onSaved = vi.fn();
    const draft = validDraft({ role: "admin" });
    const before = snapshot(draft);
    await submitCreateUser(draft, onSaved);
    expect(onSaved).not.toHaveBeenCalled();
    expect(snapshot(draft)).toEqual(before);
    expect(draft.submitStatus).toBe("idle");
  });

  it("a 409 shows through the merged view on the username key — DoD-6", async () => {
    stubFetch(usernameTaken);
    const draft = validDraft();
    await submitCreateUser(draft, vi.fn());
    expect(createUserErrors(draft).username).toMatch(USERNAME_TAKEN);
    expect(createUserErrors(draft).general).toBeUndefined();
  });

  it("a 409 raises no notification — DoD-6", async () => {
    stubFetch(usernameTaken);
    await submitCreateUser(validDraft(), vi.fn());
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("submitCreateUser — every other failure lands on the general key", () => {
  const FAILURES: Array<[string, () => Promise<Response>]> = [
    ["a 500 envelope", envelope("internal_error", "Creation exploded zq-500.", 500)],
    ["a 403 envelope", envelope("insufficient_role", "You need a higher role zq-403.", 403)],
    ["a 404 envelope", envelope("not_found", "Nothing here zq-404.", 404)],
    ["a 400 envelope whose message talks about the password", envelope("bad_request", "Password too weak zq-400.", 400)],
    ["a 500 envelope whose message says the username is taken", envelope("internal_error", "That username is already taken.", 500)],
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
    ["a transport failure", transportFailure],
  ];

  it.each(FAILURES)("%s lands on the general key and nothing else — DoD-7 (D10)", async (_name, handler) => {
    stubFetch(handler);
    const draft = validDraft();
    await expect(submitCreateUser(draft, vi.fn())).resolves.toBeUndefined();
    expect(typeof draft.serverErrors.general).toBe("string");
    expect(draft.serverErrors.general).not.toBe("");
    expect(draft.serverErrors.username).toBeUndefined();
    expect(Object.keys(draft.serverErrors)).toEqual(["general"]);
    expect(draft.submitStatus).toBe("idle");
  });

  it("a 401 lands on the general key too — DoD-7", async () => {
    vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(envelope("not_authenticated", "Sign in again zq-401.", 401));
    const draft = validDraft();
    await submitCreateUser(draft, vi.fn());
    expect(typeof draft.serverErrors.general).toBe("string");
    expect(draft.serverErrors.username).toBeUndefined();
  });

  it.each(FAILURES)("%s does not invoke the saved callback and keeps the typed values — DoD-7", async (_name, handler) => {
    stubFetch(handler);
    const onSaved = vi.fn();
    const draft = validDraft();
    const before = snapshot(draft);
    await submitCreateUser(draft, onSaved);
    expect(onSaved).not.toHaveBeenCalled();
    expect(snapshot(draft)).toEqual(before);
  });

  it("no password key is ever produced — the password half of the mapping does not exist — DoD-7 (D10)", async () => {
    stubFetch(envelope("bad_request", "Password does not satisfy policy zq-400.", 400));
    const draft = validDraft();
    await submitCreateUser(draft, vi.fn());
    expect(Object.keys(draft.serverErrors)).not.toContain("password");
    expect(createUserErrors(draft).password).toBeUndefined();
  });

  it("a failure raises no notification — DoD-7", async () => {
    stubFetch(envelope("internal_error", "Creation exploded zq-500.", 500));
    await submitCreateUser(validDraft(), vi.fn());
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

});

// ---------------------------------------------------------------------------
describe("submitCreateUser — abort", () => {
  it("a pre-aborted signal writes nothing and invokes no callback — DoD-7 (Interface intent: early return on abort)", async () => {
    stubFetch(abortableNeverAnswers);
    const controller = new AbortController();
    controller.abort();
    const onSaved = vi.fn();
    const draft = validDraft();
    const before = snapshot(draft);
    await submitCreateUser(draft, onSaved, controller.signal).catch(() => undefined);
    expect(draft.serverErrors).toEqual({});
    expect(snapshot(draft)).toEqual(before);
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("a failure arriving after the abort writes no error and invokes no callback — DoD-7 (Interface intent)", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const controller = new AbortController();
    const onSaved = vi.fn();
    const draft = validDraft();
    const run = submitCreateUser(draft, onSaved, controller.signal);
    await flushMicrotasks();
    controller.abort();
    pending.resolve(jsonResponse({ error: { code: "internal_error", message: "late zq-9", detail: {} } }, 500));
    await run.catch(() => undefined);
    expect(draft.serverErrors).toEqual({});
    expect(onSaved).not.toHaveBeenCalled();
  });
});
