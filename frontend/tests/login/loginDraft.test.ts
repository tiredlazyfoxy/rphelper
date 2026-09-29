// Feature 004, step 005 — the login draft, its pure validators and its effectful submit
// (docs/plans/004.authentication-session/005.login-entry.md).
// Covers DoD-1, DoD-2, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8, DoD-9, DoD-10, DoD-11, DoD-12,
// DoD-13 at the draft level; LoginPage.test.tsx covers the rendered half.
//
// Expected values come from the step's Interface intent and Definition of done and from
// `context.md` D1, D12, D13, D14, D16. `fetch` is stubbed per test; `notifyFailure` is mocked
// at file level because spying on an ESM export is unreliable.
import { isComputedProp, isObservableProp, runInAction } from "mobx";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoginDraft, canSubmitLogin, loginClientErrors, submitLogin } from "../../src/login/loginDraft";
import { documentNavigation } from "../../src/shared/api";

const { notifyFailureSpy } = vi.hoisted(() => ({ notifyFailureSpy: vi.fn() }));
vi.mock("../../src/shared/notifyFailure", () => ({ notifyFailure: notifyFailureSpy }));

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const USERNAME = "zq-roleplayer-one";
const PASSWORD = "Tq9-login-horse-zq";
const DRAFT_FIELDS = ["username", "password", "serverErrors", "submitting"] as const;

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

const signedIn = (role: string = "roleplayer") => () =>
  Promise.resolve(jsonResponse({ id: "7340032000000009", username: USERNAME, role }, 200));

const invalidCredentials = (message = "Invalid username or password.") =>
  envelope("invalid_credentials", message, 400);

const transportFailure = () => Promise.reject(new TypeError("Failed to fetch"));

const malformed502 = () =>
  Promise.resolve(
    new Response("<html><body>502 Bad Gateway</body></html>", {
      status: 502,
      headers: { "Content-Type": "text/html" },
    }),
  );

const fastApi422 = () =>
  Promise.resolve(
    jsonResponse({ detail: [{ type: "string_too_short", loc: ["body", "username"], msg: "too short", input: "" }] }, 422),
  );

const backend500 = envelope("internal_error", "Login exploded zq-42.", 500);

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

function makeDraft(fields: { username?: string; password?: string } = {}): LoginDraft {
  const draft = new LoginDraft();
  runInAction(() => {
    draft.username = fields.username ?? "";
    draft.password = fields.password ?? "";
  });
  return draft;
}

function validDraft(): LoginDraft {
  return makeDraft({ username: USERNAME, password: PASSWORD });
}

function requestPath(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost").pathname;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function requestBodyText(init?: RequestInit): string {
  const raw = init?.body;
  if (typeof raw !== "string") {
    throw new Error(`request body is not a JSON string: ${String(raw)}`);
  }
  return raw;
}

function requestJson(init?: RequestInit): unknown {
  return JSON.parse(requestBodyText(init));
}

async function flushMicrotasks(): Promise<void> {
  for (let i = 0; i < 4; i += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

// ---------------------------------------------------------------------------
describe("loginClientErrors", () => {
  it("reports no error for a filled draft — DoD-1", () => {
    expect(loginClientErrors(validDraft())).toEqual({});
  });

  it("reports a username error for an empty username — DoD-1", () => {
    const errors = loginClientErrors(makeDraft({ username: "", password: PASSWORD }));
    expect(errors.username).toBeTruthy();
  });

  it.each([" ", "   ", "\t", " \n\t "])("reports a username error for a whitespace-only username %j — DoD-1", (username) => {
    const errors = loginClientErrors(makeDraft({ username, password: PASSWORD }));
    expect(errors.username).toBeTruthy();
  });

  it("reports a password error for an empty password — DoD-1", () => {
    const errors = loginClientErrors(makeDraft({ username: USERNAME, password: "" }));
    expect(errors.password).toBeTruthy();
  });

  it("an empty username reports only the username — DoD-1", () => {
    const errors = loginClientErrors(makeDraft({ username: "", password: PASSWORD }));
    expect(Object.keys(errors)).toEqual(["username"]);
  });

  it("an empty password reports only the password — DoD-1", () => {
    const errors = loginClientErrors(makeDraft({ username: USERNAME, password: "" }));
    expect(Object.keys(errors)).toEqual(["password"]);
  });

  it("an entirely empty draft reports username and password errors — DoD-1", () => {
    const errors = loginClientErrors(new LoginDraft());
    expect(errors.username).toBeTruthy();
    expect(errors.password).toBeTruthy();
  });

  it("a username with surrounding whitespace but content is not an error — DoD-1", () => {
    expect(loginClientErrors(makeDraft({ username: `  ${USERNAME}  `, password: PASSWORD }))).toEqual({});
  });

  it("imposes no password policy: a one-character password is valid — DoD-1", () => {
    expect(loginClientErrors(makeDraft({ username: "a", password: "x" }))).toEqual({});
  });

  it("is pure — it changes nothing on the draft, including the untrimmed username — DoD-1", () => {
    const draft = makeDraft({ username: `  ${USERNAME} `, password: ` ${PASSWORD} ` });
    loginClientErrors(draft);
    expect(draft.username).toBe(`  ${USERNAME} `);
    expect(draft.password).toBe(` ${PASSWORD} `);
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitting).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("canSubmitLogin", () => {
  it("is true for a valid draft with no submit in flight — DoD-2", () => {
    expect(canSubmitLogin(validDraft())).toBe(true);
  });

  it.each<[string, { username: string; password: string }]>([
    ["an empty username", { username: "", password: PASSWORD }],
    ["a whitespace-only username", { username: "   ", password: PASSWORD }],
    ["an empty password", { username: USERNAME, password: "" }],
    ["an empty draft", { username: "", password: "" }],
  ])("is false for %s — DoD-2", (_name, fields) => {
    expect(canSubmitLogin(makeDraft(fields))).toBe(false);
  });

  it("is false for a valid draft while a submit is in flight — DoD-2", () => {
    const draft = validDraft();
    runInAction(() => {
      draft.submitting = true;
    });
    expect(canSubmitLogin(draft)).toBe(false);
  });

  it("is false for an invalid draft while a submit is in flight — DoD-2", () => {
    const draft = makeDraft({ username: "", password: PASSWORD });
    runInAction(() => {
      draft.submitting = true;
    });
    expect(canSubmitLogin(draft)).toBe(false);
  });

  it("is pure — it writes nothing onto the draft — DoD-2", () => {
    const draft = validDraft();
    canSubmitLogin(draft);
    expect(draft.submitting).toBe(false);
    expect(draft.serverErrors).toEqual({});
  });

  it("the in-flight flag is raised while the request is pending and lowered after — DoD-2", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const draft = validDraft();
    const outcome = submitLogin(draft);
    await flushMicrotasks();
    expect(draft.submitting).toBe(true);
    expect(canSubmitLogin(draft)).toBe(false);
    pending.resolve(await signedIn()());
    await outcome;
    expect(draft.submitting).toBe(false);
    expect(canSubmitLogin(draft)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("submitLogin — the request", () => {
  it("issues exactly one POST /api/auth/login — DoD-4, DoD-12", async () => {
    const fetchMock = stubFetch(signedIn());
    await submitLogin(validDraft());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0];
    expect(requestPath(input)).toBe("/api/auth/login");
    expect(requestMethod(input, init)).toBe("POST");
  });

  it("the body carries the username and password and nothing else — DoD-4 (US-004.AC-1)", async () => {
    const fetchMock = stubFetch(signedIn());
    await submitLogin(validDraft());
    const body = requestJson(fetchMock.mock.calls[0][1]);
    expect(body).toEqual({ username: USERNAME, password: PASSWORD });
    expect(Object.keys(body as Record<string, unknown>).sort()).toEqual(["password", "username"]);
  });

  it.each<[string, string, string]>([
    ["surrounding whitespace", "  Spaced User  ", "  pass with spaces  "],
    ["mixed case", "MiXeD.CaSe.User", "PaSsWoRd-CaSe"],
    ["tabs and inner whitespace", "\tname  with\tgaps ", " \tpw\t "],
    ["a decomposed Unicode accent (NFD, not NFC)", "José", "café-secret"],
    ["a composed Unicode accent (NFC, not NFD)", "José", "café-secret"],
    ["full-width characters", "ｕｓｅｒ", "ｐａｓｓ"],
  ])("sends %s byte-for-byte as typed, with no normalization — DoD-4 (context.md D13)", async (_name, username, password) => {
    const fetchMock = stubFetch(signedIn());
    await submitLogin(makeDraft({ username, password }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = requestJson(fetchMock.mock.calls[0][1]) as Record<string, unknown>;
    expect(body).toEqual({ username, password });
    expect(body.username).toBe(username);
    expect(body.password).toBe(password);
    expect((body.username as string).length).toBe(username.length);
    expect((body.password as string).length).toBe(password.length);
  });

  it("sending does not rewrite the draft's fields — DoD-4 (context.md D13)", async () => {
    stubFetch(signedIn());
    const draft = makeDraft({ username: "  Padded  ", password: " P w " });
    await submitLogin(draft);
    expect(draft.username).toBe("  Padded  ");
    expect(draft.password).toBe(" P w ");
  });

  it("a 200 resolves to the signed-in outcome — DoD-5", async () => {
    stubFetch(signedIn());
    await expect(submitLogin(validDraft())).resolves.toBe("signedIn");
  });

  it("the signed-in path leaves no server error and no submit in flight — DoD-5", async () => {
    stubFetch(signedIn());
    const draft = validDraft();
    await submitLogin(draft);
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitting).toBe(false);
  });

  it("performs no navigation of its own on success — DoD-5", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(signedIn());
    await submitLogin(validDraft());
    expect(assignSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("submitLogin — no role branch, no response read", () => {
  it.each<[string, () => Promise<Response>]>([
    ["an admin identity", signedIn("admin")],
    ["a roleplayer identity", signedIn("roleplayer")],
    ["an unknown role", signedIn("some-future-role")],
    ["an empty object", () => Promise.resolve(jsonResponse({}, 200))],
    ["a JSON null", () => Promise.resolve(jsonResponse(null, 200))],
    ["a JSON array", () => Promise.resolve(jsonResponse([1, 2, 3], 200))],
    ["an empty 200 body", () => Promise.resolve(new Response(null, { status: 200 }))],
    ["a 204", () => Promise.resolve(new Response(null, { status: 204 }))],
  ])("a success with %s resolves to the same signed-in outcome — DoD-6 (US-004.AC-2, context.md D12)", async (_name, handler) => {
    stubFetch(handler);
    const draft = validDraft();
    await expect(submitLogin(draft)).resolves.toBe("signedIn");
    expect(draft.serverErrors).toEqual({});
  });
});

// ---------------------------------------------------------------------------
describe("submitLogin — the invalid_credentials refusal", () => {
  it("resolves to failed with a non-empty message on the general key — DoD-7 (US-005.AC-2)", async () => {
    stubFetch(invalidCredentials());
    const draft = validDraft();
    await expect(submitLogin(draft)).resolves.toBe("failed");
    expect(typeof draft.serverErrors.general).toBe("string");
    expect(draft.serverErrors.general).not.toBe("");
    expect(draft.submitting).toBe(false);
  });

  it("places no message on the username or password key — DoD-7", async () => {
    stubFetch(invalidCredentials());
    const draft = validDraft();
    await submitLogin(draft);
    expect(draft.serverErrors.username).toBeUndefined();
    expect(draft.serverErrors.password).toBeUndefined();
    expect(Object.keys(draft.serverErrors)).toEqual(["general"]);
  });

  it("even a refusal carrying a field-shaped detail lands on the general key only — DoD-7", async () => {
    stubFetch(envelope("invalid_credentials", "Invalid username or password.", 400, { field: "username" }));
    const draft = validDraft();
    await submitLogin(draft);
    expect(Object.keys(draft.serverErrors)).toEqual(["general"]);
  });

  it("the message is one fixed message, independent of the server's prose — DoD-7", async () => {
    stubFetch(invalidCredentials("Server prose zq-alpha-81."));
    const first = validDraft();
    await submitLogin(first);

    vi.unstubAllGlobals();
    stubFetch(invalidCredentials("Completely different prose zq-beta-82."));
    const second = validDraft();
    await submitLogin(second);

    expect(first.serverErrors.general).toBeTruthy();
    expect(first.serverErrors.general).toBe(second.serverErrors.general);
    expect(first.serverErrors.general).not.toContain("zq-alpha-81");
    expect(second.serverErrors.general).not.toContain("zq-beta-82");
  });

  it("the refusal preserves the entered username and leaves the draft submittable — DoD-7", async () => {
    stubFetch(invalidCredentials());
    const draft = validDraft();
    await submitLogin(draft);
    expect(draft.username).toBe(USERNAME);
    expect(canSubmitLogin(draft)).toBe(true);
  });

  it("performs no navigation on the refusal — DoD-7", async () => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(invalidCredentials());
    await submitLogin(validDraft());
    expect(assignSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("submitLogin — a disabled account is indistinguishable", () => {
  // The backend answers a disabled account with the same invalid_credentials refusal (D1). Even
  // if the server's prose or detail differed, the client maps by code and must render the same.
  it("a refusal whose prose or detail mentions a disabled account yields the same draft state — DoD-8 (US-006.AC-2, context.md D1)", async () => {
    stubFetch(invalidCredentials());
    const wrongPassword = validDraft();
    const wrongOutcome = await submitLogin(wrongPassword);

    vi.unstubAllGlobals();
    stubFetch(envelope("invalid_credentials", "This account is disabled zq-dis-1.", 400, { reason: "account_disabled" }));
    const disabled = validDraft();
    const disabledOutcome = await submitLogin(disabled);

    expect(disabledOutcome).toBe(wrongOutcome);
    expect(disabled.serverErrors).toEqual(wrongPassword.serverErrors);
    expect(disabled.serverErrors.general ?? "").not.toMatch(/disabled/i);
    expect(disabled.username).toBe(wrongPassword.username);
    expect(disabled.submitting).toBe(wrongPassword.submitting);
  });
});

// ---------------------------------------------------------------------------
describe("submitLogin — every other failure", () => {
  it.each<[string, () => Promise<Response>]>([
    ["a transport failure", transportFailure],
    ["a malformed (non-envelope) body at 502", malformed502],
    ["FastAPI's own 422 body", fastApi422],
    ["a backend error envelope at 500", backend500],
    ["another code at 400", envelope("some_other_code", "Other zq-77.", 400)],
  ])("%s resolves to failed and lands on the general key only — DoD-9 (context.md D14)", async (_name, handler) => {
    stubFetch(handler);
    const draft = validDraft();
    await expect(submitLogin(draft)).resolves.toBe("failed");
    expect(typeof draft.serverErrors.general).toBe("string");
    expect(draft.serverErrors.general).not.toBe("");
    expect(Object.keys(draft.serverErrors)).toEqual(["general"]);
    expect(draft.submitting).toBe(false);
    expect(draft.username).toBe(USERNAME);
  });

  it.each<[string, () => Promise<Response>]>([
    ["a transport failure", transportFailure],
    ["a malformed body at 502", malformed502],
    ["FastAPI's own 422", fastApi422],
  ])("%s performs no navigation — DoD-9", async (_name, handler) => {
    const assignSpy = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
    stubFetch(handler);
    await submitLogin(validDraft());
    expect(assignSpy).not.toHaveBeenCalled();
  });

  it("after a failure the draft may be submitted again — DoD-9", async () => {
    stubFetch(transportFailure);
    const draft = validDraft();
    await submitLogin(draft);
    expect(canSubmitLogin(draft)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("submitLogin — no field value in the general message", () => {
  it.each<[string, () => Promise<Response>]>([
    ["the refusal", invalidCredentials()],
    ["a transport failure", transportFailure],
    ["a malformed body at 502", malformed502],
    ["FastAPI's own 422", fastApi422],
    ["a backend error envelope", backend500],
  ])("after %s the general message contains neither the username nor the password — DoD-10", async (_name, handler) => {
    stubFetch(handler);
    const draft = validDraft();
    await submitLogin(draft);
    expect(draft.serverErrors.general ?? "").not.toContain(USERNAME);
    expect(draft.serverErrors.general ?? "").not.toContain(PASSWORD);
  });

  it("a server message echoing both values does not carry them into the general message — DoD-10", async () => {
    stubFetch(envelope("internal_error", `Failed for ${USERNAME} using ${PASSWORD}.`, 500));
    const draft = validDraft();
    await submitLogin(draft);
    expect(draft.serverErrors.general).toBeTruthy();
    expect(draft.serverErrors.general ?? "").not.toContain(USERNAME);
    expect(draft.serverErrors.general ?? "").not.toContain(PASSWORD);
  });

  it("a refusal message echoing both values does not carry them into the general message — DoD-10", async () => {
    stubFetch(invalidCredentials(`No account ${USERNAME} with password ${PASSWORD}.`));
    const draft = validDraft();
    await submitLogin(draft);
    expect(draft.serverErrors.general).toBeTruthy();
    expect(draft.serverErrors.general ?? "").not.toContain(USERNAME);
    expect(draft.serverErrors.general ?? "").not.toContain(PASSWORD);
  });
});

// ---------------------------------------------------------------------------
describe("submitLogin — abort", () => {
  it("a pre-aborted signal resolves, does not sign in, and writes nothing onto the draft — DoD-11", async () => {
    stubFetch(abortableNeverAnswers);
    const controller = new AbortController();
    controller.abort();
    const draft = validDraft();
    await expect(submitLogin(draft, controller.signal)).resolves.not.toBe("signedIn");
    expect(draft.serverErrors).toEqual({});
    expect(draft.username).toBe(USERNAME);
    expect(draft.password).toBe(PASSWORD);
  });

  it("a pre-aborted signal writes no error even when the stubbed request answers a failure — DoD-11", async () => {
    stubFetch(backend500);
    const controller = new AbortController();
    controller.abort();
    const draft = validDraft();
    await submitLogin(draft, controller.signal);
    expect(draft.serverErrors).toEqual({});
  });

  it("aborting mid-flight resolves, does not sign in, and writes no error onto the draft — DoD-11", async () => {
    stubFetch(abortableNeverAnswers);
    const controller = new AbortController();
    const draft = validDraft();
    const outcome = submitLogin(draft, controller.signal);
    await flushMicrotasks();
    controller.abort();
    await expect(outcome).resolves.not.toBe("signedIn");
    expect(draft.serverErrors).toEqual({});
  });

  it("a refusal arriving after the abort writes no error onto the draft — DoD-11", async () => {
    const pending = deferred<Response>();
    stubFetch(() => pending.promise);
    const controller = new AbortController();
    const draft = validDraft();
    const outcome = submitLogin(draft, controller.signal);
    await flushMicrotasks();
    controller.abort();
    pending.resolve(await invalidCredentials()());
    await outcome;
    expect(draft.serverErrors).toEqual({});
  });
});

// ---------------------------------------------------------------------------
describe("no notification and a pure data class", () => {
  it.each<[string, () => Promise<Response>]>([
    ["signed in", signedIn()],
    ["refused", invalidCredentials()],
    ["a backend failure", backend500],
    ["a transport failure", transportFailure],
    ["a malformed body at 502", malformed502],
    ["FastAPI's own 422", fastApi422],
  ])("submitting (%s) calls notifyFailure nowhere — DoD-13", async (_name, handler) => {
    stubFetch(handler);
    await submitLogin(validDraft());
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("an aborted submit calls notifyFailure nowhere — DoD-13", async () => {
    stubFetch(abortableNeverAnswers);
    const controller = new AbortController();
    controller.abort();
    await submitLogin(validDraft(), controller.signal);
    expect(notifyFailureSpy).not.toHaveBeenCalled();
  });

  it("the draft class prototype carries no method and no getter — DoD-13", () => {
    expect(Object.getOwnPropertyNames(LoginDraft.prototype)).toEqual(["constructor"]);
  });

  it("a fresh draft holds the four documented fields, each observable and none computed — DoD-13", () => {
    const draft = new LoginDraft();
    for (const name of DRAFT_FIELDS) {
      expect(isObservableProp(draft, name), `field ${name}`).toBe(true);
      expect(isComputedProp(draft, name), `field ${name}`).toBe(false);
    }
  });

  it("a fresh draft starts empty with no server error and no submit in flight — DoD-13", () => {
    const draft = new LoginDraft();
    expect(draft.username).toBe("");
    expect(draft.password).toBe("");
    expect(draft.serverErrors).toEqual({});
    expect(draft.submitting).toBe(false);
  });

  it("no own property of a draft is a function or a computed value — DoD-13", () => {
    const draft = new LoginDraft();
    for (const name of Object.getOwnPropertyNames(draft)) {
      const descriptor = Object.getOwnPropertyDescriptor(draft, name);
      const value = descriptor && "value" in descriptor ? descriptor.value : undefined;
      expect(typeof value, `own property ${name}`).not.toBe("function");
      expect(isComputedProp(draft, name), `own property ${name}`).toBe(false);
    }
  });

  it("two drafts are independent instances — DoD-13", () => {
    const a = new LoginDraft();
    const b = new LoginDraft();
    runInAction(() => {
      a.username = "only-a";
      a.serverErrors = { general: "only-a" };
    });
    expect(b.username).toBe("");
    expect(b.serverErrors).toEqual({});
  });
});
