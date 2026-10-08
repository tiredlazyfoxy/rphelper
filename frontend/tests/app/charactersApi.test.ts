// Feature 009, step 004 — the characters API client (DoD-1..DoD-4).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 004.context.md and context.md's "Wire contract — /api/characters" and the "Ids are
// strings" constraint. The six calls address the wire contract's routes exactly: the
// listing takes ?include_archived=true only when asked, a PATCH carries only the keys it
// was given, and nothing coerces an id — a decimal string beyond Number.MAX_SAFE_INTEGER
// must survive a round trip character for character. Failures are the shared client's
// ApiErrors, rethrown unchanged.
import { afterEach, describe, expect, it, vi } from "vitest";
import { isApiError } from "../../src/shared/apiError";
import {
  archiveCharacter,
  type Character,
  createCharacter,
  fetchCharacter,
  fetchCharacters,
  isArchived,
  restoreCharacter,
  updateCharacter,
} from "../../src/app/charactersApi";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const LIST_PATH = "/api/characters";
// 7250000000000000001 > Number.MAX_SAFE_INTEGER: a silent numeric coercion would change it.
const BIG_ID = "7250000000000000001";
const OTHER_ID = "7250000000000000002";

const ALMA: Character = {
  id: BIG_ID,
  name: "Alma Vist",
  sheet: "# Alma\n\nA cartographer who never finishes a map.",
  archived_at: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};
const BRENN: Character = {
  id: OTHER_ID,
  name: "Brenn Oduya",
  sheet: "# Brenn\n\nKeeps a ledger of favours owed.",
  archived_at: "2026-03-20T18:04:11.000000+00:00",
  created_at: "2026-03-10T11:00:00.000000+00:00",
  updated_at: "2026-03-20T18:04:11.000000+00:00",
};

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

function serve(body: unknown, status = 200) {
  return stubFetch(() => Promise.resolve(jsonResponse(body, status)));
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(raw, "http://localhost");
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

type Seen = { method: string; path: string; search: string };

function seen(mock: ReturnType<typeof stubFetch>): Seen[] {
  return mock.mock.calls.map(([input, init]) => {
    const url = requestUrl(input);
    return { method: requestMethod(input, init), path: url.pathname, search: url.search };
  });
}

/** The JSON body of the n-th request, or undefined when none was sent. */
function sentBody(mock: ReturnType<typeof stubFetch>, index = 0): unknown {
  const raw = mock.mock.calls[index]?.[1]?.body;
  if (raw === undefined || raw === null) return undefined;
  return typeof raw === "string" ? (JSON.parse(raw) as unknown) : raw;
}

function envelope(code: string, message: string): unknown {
  return { error: { code, message, detail: {} } };
}

// ---------------------------------------------------------------------------
describe("fetchCharacters", () => {
  it("requests exactly GET /api/characters with no query string when includeArchived is false — DoD-1", async () => {
    const mock = serve({ characters: [ALMA] });
    await fetchCharacters(false);
    expect(seen(mock)).toEqual([{ method: "GET", path: LIST_PATH, search: "" }]);
  });

  it("requests exactly GET /api/characters?include_archived=true when includeArchived is true — DoD-1", async () => {
    const mock = serve({ characters: [ALMA, BRENN] });
    await fetchCharacters(true);
    expect(seen(mock)).toEqual([
      { method: "GET", path: LIST_PATH, search: "?include_archived=true" },
    ]);
  });

  it("resolves to the payload's characters array, unwrapped and in the payload's order — DoD-1", async () => {
    serve({ characters: [ALMA, BRENN] });
    await expect(fetchCharacters(true)).resolves.toEqual([ALMA, BRENN]);
  });

  it("resolves to an empty array for an empty listing — DoD-1", async () => {
    serve({ characters: [] });
    await expect(fetchCharacters(false)).resolves.toEqual([]);
  });

  it("keeps every id the identical string the payload carried, past MAX_SAFE_INTEGER — DoD-1", async () => {
    serve({ characters: [ALMA, BRENN] });
    const rows = await fetchCharacters(true);
    expect(rows.map((row) => row.id)).toEqual([BIG_ID, OTHER_ID]);
    expect(typeof rows[0].id).toBe("string");
    expect(rows[0].id).toBe(BIG_ID);
  });
});

// ---------------------------------------------------------------------------
describe("the five id-addressed calls", () => {
  it("fetchCharacter GETs /api/characters/<id> with the id verbatim and resolves to the character — DoD-2", async () => {
    const mock = serve(ALMA);
    await expect(fetchCharacter(BIG_ID)).resolves.toEqual(ALMA);
    expect(seen(mock)).toEqual([
      { method: "GET", path: `${LIST_PATH}/${BIG_ID}`, search: "" },
    ]);
  });

  it("createCharacter POSTs /api/characters with the JSON body { name, sheet } — DoD-2", async () => {
    const mock = serve(ALMA, 201);
    await expect(createCharacter({ name: ALMA.name, sheet: ALMA.sheet })).resolves.toEqual(ALMA);
    expect(seen(mock)).toEqual([{ method: "POST", path: LIST_PATH, search: "" }]);
    expect(sentBody(mock)).toEqual({ name: ALMA.name, sheet: ALMA.sheet });
    expect(Object.keys(sentBody(mock) as object).sort()).toEqual(["name", "sheet"]);
  });

  it("updateCharacter PATCHes /api/characters/<id> with only the name it was given — DoD-2", async () => {
    const renamed: Character = { ...ALMA, name: "Alma Vistaro" };
    const mock = serve(renamed);
    await expect(updateCharacter(BIG_ID, { name: "Alma Vistaro" })).resolves.toEqual(renamed);
    expect(seen(mock)).toEqual([
      { method: "PATCH", path: `${LIST_PATH}/${BIG_ID}`, search: "" },
    ]);
    expect(Object.keys(sentBody(mock) as object)).toEqual(["name"]);
    expect(sentBody(mock)).toEqual({ name: "Alma Vistaro" });
  });

  it("updateCharacter PATCHes with only the sheet it was given — DoD-2", async () => {
    const edited: Character = { ...ALMA, sheet: "# Alma\n\nFinished one map." };
    const mock = serve(edited);
    await expect(updateCharacter(BIG_ID, { sheet: edited.sheet })).resolves.toEqual(edited);
    expect(Object.keys(sentBody(mock) as object)).toEqual(["sheet"]);
    expect(sentBody(mock)).toEqual({ sheet: edited.sheet });
  });

  it("updateCharacter PATCHes both keys when both are given — DoD-2", async () => {
    const edited: Character = { ...ALMA, name: "Alma V.", sheet: "# Alma\n\nTwo maps." };
    const mock = serve(edited);
    await updateCharacter(BIG_ID, { name: edited.name, sheet: edited.sheet });
    expect(Object.keys(sentBody(mock) as object).sort()).toEqual(["name", "sheet"]);
    expect(sentBody(mock)).toEqual({ name: edited.name, sheet: edited.sheet });
  });

  it("updateCharacter with an empty patch sends a body with no keys — DoD-2", async () => {
    const mock = serve(ALMA);
    await expect(updateCharacter(BIG_ID, {})).resolves.toEqual(ALMA);
    const body = sentBody(mock);
    expect(body === undefined ? [] : Object.keys(body as object)).toEqual([]);
  });

  it("archiveCharacter POSTs /api/characters/<id>/archive and resolves to the character — DoD-2", async () => {
    const archived: Character = { ...ALMA, archived_at: "2026-03-21T07:00:00.000000+00:00" };
    const mock = serve(archived);
    await expect(archiveCharacter(BIG_ID)).resolves.toEqual(archived);
    expect(seen(mock)).toEqual([
      { method: "POST", path: `${LIST_PATH}/${BIG_ID}/archive`, search: "" },
    ]);
  });

  it("restoreCharacter POSTs /api/characters/<id>/restore and resolves to the character — DoD-2", async () => {
    const mock = serve(ALMA);
    await expect(restoreCharacter(BIG_ID)).resolves.toEqual(ALMA);
    expect(seen(mock)).toEqual([
      { method: "POST", path: `${LIST_PATH}/${BIG_ID}/restore`, search: "" },
    ]);
  });

  it("an id beyond MAX_SAFE_INTEGER reaches every route unchanged — DoD-2", async () => {
    for (const call of [
      () => fetchCharacter(BIG_ID),
      () => updateCharacter(BIG_ID, { name: "x" }),
      () => archiveCharacter(BIG_ID),
      () => restoreCharacter(BIG_ID),
    ]) {
      const mock = serve(ALMA);
      await call();
      expect(seen(mock)[0].path.startsWith(`${LIST_PATH}/${BIG_ID}`)).toBe(true);
      vi.unstubAllGlobals();
    }
  });
});

// ---------------------------------------------------------------------------
describe("failures are the shared client's ApiErrors", () => {
  it("a 404 character_not_found envelope rejects fetchCharacter with that ApiError code — DoD-3", async () => {
    serve(envelope("character_not_found", "That character does not exist."), 404);
    const error: unknown = await fetchCharacter(BIG_ID).then(
      () => {
        throw new Error("fetchCharacter resolved, but the route answered 404");
      },
      (reason: unknown) => reason,
    );
    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.code : null).toBe("character_not_found");
    expect(isApiError(error) ? error.status : null).toBe(404);
  });

  it("the same 404 rejects every other id-addressed call with character_not_found — DoD-3", async () => {
    for (const call of [
      () => updateCharacter(BIG_ID, { name: "x" }),
      () => archiveCharacter(BIG_ID),
      () => restoreCharacter(BIG_ID),
    ]) {
      serve(envelope("character_not_found", "That character does not exist."), 404);
      const error: unknown = await call().then(
        () => {
          throw new Error("the call resolved, but the route answered 404");
        },
        (reason: unknown) => reason,
      );
      expect(isApiError(error)).toBe(true);
      expect(isApiError(error) ? error.code : null).toBe("character_not_found");
      vi.unstubAllGlobals();
    }
  });
});

// ---------------------------------------------------------------------------
describe("isArchived", () => {
  it("is true when archived_at is a string — DoD-4", () => {
    expect(isArchived(BRENN)).toBe(true);
  });

  it("is false when archived_at is null — DoD-4", () => {
    expect(isArchived(ALMA)).toBe(false);
  });
});
