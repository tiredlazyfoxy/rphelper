// Feature 008, step 005 — the boot state module's classification, probe and the
// case-collision guard (DoD-1, DoD-2, DoD-3, DoD-14).
// DoD-4..DoD-10 live in ./AppBoot.test.tsx; DoD-11 and DoD-12 in ../entries.test.tsx.
// DoD-13 is [manual/live] and has no test here.
//
// No component and no timers here. The thrown values DoD-1 classifies are produced by the
// real client (`fetchCurrentUser` over a stubbed `fetch`), so each fixture is the very value
// `shared/api.ts` throws for that condition rather than a hand-made look-alike; `fetch` is
// stubbed per test with `vi.stubGlobal` and `documentNavigation.assign` is a restored
// `vi.spyOn` (the client itself navigates on a 401 — context.md D13).
//
// DoD-14 is a filename scan, not a behaviour test. "Module path" is the extensionless
// specifier two resolvers disagree about (005.context.md: "Lowercased, `appbootstate`,
// `appboot`, `appbootscreens` and `main` are all distinct"), so the comparison strips the
// `.ts` / `.tsx` extension before lowercasing — `appBoot.ts` beside `AppBoot.tsx` is the
// pair that must be flagged.
import { readdirSync } from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { AppBootState, classifyAppBootError, probeCurrentUser } from "../../src/app/appBootState";
import { documentNavigation } from "../../src/shared/api";
import { isApiError, type ApiError } from "../../src/shared/apiError";
import { fetchCurrentUser, type CurrentUser } from "../../src/shared/currentUser";

const ME_PATH = "/api/me";

const ROLES: Array<CurrentUser["role"]> = ["roleplayer", "admin"];

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

let navigate: MockInstance<(url: string) => void>;

beforeEach(() => {
  navigate = vi.spyOn(documentNavigation, "assign").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ----------------------------------------------------------------- fetch stubs

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

function identity(role: CurrentUser["role"], id = "9007199254740993"): CurrentUser {
  return { id, username: "mira", role };
}

const answerIdentity = (role: CurrentUser["role"]): FetchFn => () =>
  Promise.resolve(jsonResponse(identity(role), 200));

const answerEnvelope = (status: number, code: string, message: string): FetchFn => () =>
  Promise.resolve(jsonResponse({ error: { code, message, detail: {} } }, status));

/** No session: the backend's 401 envelope (context.md D13). */
const answer401: FetchFn = answerEnvelope(401, "not_authenticated", "You are not signed in.");

const answer403: FetchFn = answerEnvelope(403, "forbidden", "You may not do that.");

const answer500: FetchFn = answerEnvelope(500, "internal_error", "Something went wrong.");

/** A gateway's own 502 page — a response the client cannot decode into an envelope. */
const malformed502: FetchFn = () =>
  Promise.resolve(
    new Response("<html><body>502 Bad Gateway</body></html>", {
      status: 502,
      headers: { "Content-Type": "text/html" },
    }),
  );

const transportFailure: FetchFn = () => Promise.reject(new TypeError("Failed to fetch"));

function requestPath(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost").pathname;
}

function mePaths(mock: ReturnType<typeof stubFetch>): string[] {
  return mock.mock.calls.map(([input]) => requestPath(input)).filter((p) => p === ME_PATH);
}

const SETTLED = Symbol("settled");

/** The value `fetchCurrentUser` throws when `/api/me` answers this way. */
async function thrownByClient(impl: FetchFn): Promise<unknown> {
  stubFetch(impl);
  const outcome = await fetchCurrentUser().then(
    () => SETTLED,
    (error: unknown) => error,
  );
  expect(outcome, "the stubbed /api/me was expected to make the client throw").not.toBe(SETTLED);
  return outcome;
}

function codeOf(error: unknown): string {
  expect(isApiError(error)).toBe(true);
  return (error as ApiError).code;
}

// ---------------------------------------------------------------------------
describe("classifyAppBootError maps a thrown value to one of the three outcomes", () => {
  it("a 401 whose code is not_authenticated is unauthenticated — DoD-1", async () => {
    const error = await thrownByClient(answer401);

    expect(codeOf(error)).toBe("not_authenticated");
    expect((error as ApiError).status).toBe(401);
    expect(classifyAppBootError(error)).toBe("unauthenticated");
  });

  it("the client's transport-failure ApiError is not-ready — DoD-1", async () => {
    const error = await thrownByClient(transportFailure);

    expect(isApiError(error)).toBe(true);
    expect(classifyAppBootError(error)).toBe("not-ready");
  });

  it("a malformed-body ApiError at status 502 is not-ready — DoD-1", async () => {
    const error = await thrownByClient(malformed502);

    expect(isApiError(error)).toBe(true);
    expect((error as ApiError).status).toBe(502);
    expect(classifyAppBootError(error)).toBe("not-ready");
  });

  it("a well-formed 403 envelope is failed — DoD-1", async () => {
    const error = await thrownByClient(answer403);

    expect(codeOf(error)).toBe("forbidden");
    expect(classifyAppBootError(error)).toBe("failed");
  });

  it("a well-formed 500 envelope is failed — DoD-1", async () => {
    const error = await thrownByClient(answer500);

    expect(codeOf(error)).toBe("internal_error");
    expect(classifyAppBootError(error)).toBe("failed");
  });

  it("a plain Error is failed — DoD-1", () => {
    expect(classifyAppBootError(new Error("boom"))).toBe("failed");
  });

  it("a thrown non-Error value is failed too — DoD-1", () => {
    expect(classifyAppBootError("boom")).toBe("failed");
    expect(classifyAppBootError(null)).toBe("failed");
    expect(classifyAppBootError({ code: "not_authenticated" })).toBe("failed");
  });

  it("classifies an already-thrown value with no request of its own — DoD-1", async () => {
    const error = await thrownByClient(answer403);
    const fetchMock = stubFetch(answerIdentity("admin"));

    expect(classifyAppBootError(error)).toBe("failed");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("probeCurrentUser writes a successful identity into the state", () => {
  it("a fresh boot state is probing with no user — DoD-2", () => {
    const state = new AppBootState();

    expect(state.status).toBe("probing");
    expect(state.user).toBeNull();
  });

  it.each(ROLES)("a %s identity is written as ready — DoD-2", async (role) => {
    stubFetch(answerIdentity(role));
    const state = new AppBootState();

    await probeCurrentUser(state);

    expect(state.status).toBe("ready");
    expect(state.user).toEqual(identity(role));
  });

  it("keeps the fetched id a string — DoD-2", async () => {
    stubFetch(answerIdentity("roleplayer"));
    const state = new AppBootState();

    await probeCurrentUser(state);

    expect(typeof state.user?.id).toBe("string");
    expect(state.user?.id).toBe("9007199254740993");
  });

  it("issues exactly one GET /api/me — DoD-2", async () => {
    const fetchMock = stubFetch(answerIdentity("admin"));
    const state = new AppBootState();

    await probeCurrentUser(state);

    expect(mePaths(fetchMock)).toEqual([ME_PATH]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0]?.[1];
    expect((init?.method ?? "GET").toUpperCase()).toBe("GET");
  });

  it("a successful probe navigates nothing — DoD-2", async () => {
    stubFetch(answerIdentity("roleplayer"));
    const state = new AppBootState();

    await probeCurrentUser(state);

    expect(state.status).toBe("ready");
    expect(navigate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe("probeCurrentUser writes the classified outcome and never rethrows", () => {
  const FAILURES: Array<[string, FetchFn, AppBootState["status"]]> = [
    ["a 401 envelope", answer401, "unauthenticated"],
    ["a transport failure", transportFailure, "not-ready"],
    ["a raw 502 page", malformed502, "not-ready"],
    ["a well-formed 403", answer403, "failed"],
    ["a well-formed 500", answer500, "failed"],
  ];

  it.each(FAILURES)("%s writes its classified status — DoD-3", async (_name, answer, expected) => {
    stubFetch(answer);
    const state = new AppBootState();

    await probeCurrentUser(state);

    expect(state.status).toBe(expected);
  });

  it.each(FAILURES)("%s is never rethrown — DoD-3", async (_name, answer) => {
    stubFetch(answer);
    const state = new AppBootState();

    await expect(probeCurrentUser(state)).resolves.toBeUndefined();
  });

  it.each(FAILURES)("%s leaves the user null — DoD-3", async (_name, answer) => {
    stubFetch(answer);
    const state = new AppBootState();

    await probeCurrentUser(state);

    expect(state.user).toBeNull();
  });

  it("a response that settles after the abort is not written — DoD-3", async () => {
    let release: (response: Response) => void = () => {};
    const fetchMock = stubFetch(
      () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    );
    const state = new AppBootState();
    const controller = new AbortController();

    const probe = probeCurrentUser(state, controller.signal);
    controller.abort();
    release(jsonResponse(identity("roleplayer"), 200));
    await expect(probe).resolves.toBeUndefined();

    expect(state.status).toBe("probing");
    expect(state.user).toBeNull();
    expect(mePaths(fetchMock)).toEqual([ME_PATH]);
  });

  it("a failure that settles after the abort is not written either — DoD-3", async () => {
    let fail: (reason: unknown) => void = () => {};
    stubFetch(
      () =>
        new Promise<Response>((_resolve, reject) => {
          fail = reject;
        }),
    );
    const state = new AppBootState();
    const controller = new AbortController();

    const probe = probeCurrentUser(state, controller.signal);
    controller.abort();
    fail(new TypeError("Failed to fetch"));
    await expect(probe).resolves.toBeUndefined();

    expect(state.status).toBe("probing");
    expect(state.user).toBeNull();
  });

  it("an already-aborted signal writes nothing — DoD-3", async () => {
    stubFetch(answerIdentity("admin"));
    const state = new AppBootState();
    const controller = new AbortController();
    controller.abort();

    await expect(probeCurrentUser(state, controller.signal)).resolves.toBeUndefined();

    expect(state.status).toBe("probing");
    expect(state.user).toBeNull();
  });

  it("an abort does not stop a later probe over a fresh signal — DoD-3", async () => {
    stubFetch(answerIdentity("roleplayer"));
    const state = new AppBootState();
    const aborted = new AbortController();
    aborted.abort();
    await probeCurrentUser(state, aborted.signal);
    expect(state.status).toBe("probing");

    await probeCurrentUser(state, new AbortController().signal);

    expect(state.status).toBe("ready");
    expect(state.user).toEqual(identity("roleplayer"));
  });
});

// ---------------------------------------------------------------------------
// DoD-14 — no two module paths under src/app differ only in letter case.
const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const APP_ROOT = path.join(FRONTEND_ROOT, "src", "app");

function allFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? allFiles(full) : [full];
  });
}

function relative(file: string): string {
  return path.relative(FRONTEND_ROOT, file).split(path.sep).join("/");
}

/** Every `.ts` / `.tsx` file under `dir`, recursively, as a frontend-relative path. */
function codeFiles(dir: string): string[] {
  return allFiles(dir)
    .filter((file) => /\.(ts|tsx)$/.test(file))
    .map(relative);
}

/** The extensionless specifier two resolvers would be handed for this file. */
function modulePath(file: string): string {
  return file.replace(/\.(ts|tsx)$/, "");
}

/** `a vs b` for every group of paths that are one module path once lowercased. */
function caseCollisions(files: string[]): string[] {
  const byKey = new Map<string, string[]>();
  for (const file of files) {
    const key = modulePath(file).toLowerCase();
    byKey.set(key, [...(byKey.get(key) ?? []), file]);
  }
  return Array.from(byKey.values())
    .filter((group) => group.length > 1)
    .map((group) => group.join(" vs "));
}

describe("src/app carries no pair of module paths differing only in case", () => {
  it("the scan reaches every .ts and .tsx file under src/app, recursively — DoD-14", () => {
    const files = codeFiles(APP_ROOT);

    expect(files).toEqual(
      expect.arrayContaining([
        "src/app/main.tsx",
        "src/app/appBootState.ts",
        "src/app/AppBoot.tsx",
        "src/app/AppBootScreens.tsx",
      ]),
    );
  });

  it("no two module paths under src/app are equal once lowercased — DoD-14", () => {
    const collisions = caseCollisions(codeFiles(APP_ROOT));

    expect(collisions, collisions[0] ?? "no collisions").toEqual([]);
  });

  it("the check flags a constructed colliding pair — DoD-14", () => {
    const collisions = caseCollisions(["src/app/appBoot.ts", "src/app/AppBoot.tsx"]);

    expect(collisions).toEqual(["src/app/appBoot.ts vs src/app/AppBoot.tsx"]);
  });

  it("the check flags a collision in a nested folder too — DoD-14", () => {
    expect(caseCollisions(["src/app/parts/Panel.tsx", "src/app/parts/panel.ts"])).toHaveLength(1);
  });

  it("the check leaves paths differing by more than case alone — DoD-14", () => {
    expect(
      caseCollisions([
        "src/app/appBootState.ts",
        "src/app/AppBoot.tsx",
        "src/app/AppBootScreens.tsx",
        "src/app/main.tsx",
      ]),
    ).toEqual([]);
  });
});
