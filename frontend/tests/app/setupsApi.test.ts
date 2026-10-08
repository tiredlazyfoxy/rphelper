// Feature 010, step 004 — the setups API client (DoD-1..DoD-3).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done,
// 004.context.md and context.md's "Wire contract — setups" plus the "Ids are strings"
// constraint. The five calls address the wire contract's two path families exactly: the
// listing takes ?include_archived=true only when asked, a PATCH carries only the keys it
// was given, the two action routes are POSTs, and nothing coerces an id — a decimal string
// beyond Number.MAX_SAFE_INTEGER must survive a round trip character for character.
// Failures are the shared client's ApiErrors, rethrown unchanged.
import { afterEach, describe, expect, it, vi } from "vitest";
import { isApiError } from "../../src/shared/apiError";
import {
  archiveSetup,
  createSetup,
  fetchSetups,
  isSetupArchived,
  restoreSetup,
  type Setup,
  updateSetup,
} from "../../src/app/setupsApi";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

// Both ids are > Number.MAX_SAFE_INTEGER: a silent numeric coercion would change them.
const CHARACTER_ID = "7250000000000000001";
const SETUP_ID = "7260000000000000005";
const OTHER_SETUP_ID = "7260000000000000006";

const COLLECTION_PATH = `/api/characters/${CHARACTER_ID}/setups`;
const SETUP_PATH = `/api/setups/${SETUP_ID}`;

const TAVERN: Setup = {
  id: SETUP_ID,
  character_id: CHARACTER_ID,
  name: "The Gilded Tavern",
  description: "# The Gilded Tavern\n\nSmoke, lute strings and a bad debt.",
  archived_at: null,
  created_at: "2026-03-14T09:26:53.000000+00:00",
  updated_at: "2026-03-14T09:26:53.000000+00:00",
};
const HARBOUR: Setup = {
  id: OTHER_SETUP_ID,
  character_id: CHARACTER_ID,
  name: "Nightfall Harbour",
  description: "# Nightfall Harbour\n\nTwo ships and no harbourmaster.",
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

function bodyKeys(mock: ReturnType<typeof stubFetch>): string[] {
  const body = sentBody(mock);
  return body === undefined ? [] : Object.keys(body as object);
}

function envelope(code: string, message: string): unknown {
  return { error: { code, message, detail: {} } };
}

/** The rejection of a call that must not resolve. */
async function rejection(call: () => Promise<unknown>): Promise<unknown> {
  return call().then(
    () => {
      throw new Error("the call resolved, but the route answered an error");
    },
    (reason: unknown) => reason,
  );
}

// ---------------------------------------------------------------------------
describe("fetchSetups", () => {
  it("requests exactly GET /api/characters/<id>/setups with no query string when includeArchived is false — DoD-1", async () => {
    const mock = serve({ setups: [TAVERN] });
    await fetchSetups(CHARACTER_ID, false);
    expect(seen(mock)).toEqual([{ method: "GET", path: COLLECTION_PATH, search: "" }]);
  });

  it("requests exactly GET /api/characters/<id>/setups?include_archived=true when includeArchived is true — DoD-1", async () => {
    const mock = serve({ setups: [TAVERN, HARBOUR] });
    await fetchSetups(CHARACTER_ID, true);
    expect(seen(mock)).toEqual([
      { method: "GET", path: COLLECTION_PATH, search: "?include_archived=true" },
    ]);
  });

  it("resolves to the payload's setups array, unwrapped and in the payload's order — DoD-1", async () => {
    serve({ setups: [TAVERN, HARBOUR] });
    await expect(fetchSetups(CHARACTER_ID, true)).resolves.toEqual([TAVERN, HARBOUR]);
  });

  it("resolves to an empty array for an empty listing — DoD-1", async () => {
    serve({ setups: [] });
    await expect(fetchSetups(CHARACTER_ID, false)).resolves.toEqual([]);
  });

  it("keeps every id and character_id the identical string the payload carried, past MAX_SAFE_INTEGER — DoD-1", async () => {
    serve({ setups: [TAVERN, HARBOUR] });
    const rows = await fetchSetups(CHARACTER_ID, true);
    expect(rows.map((row) => row.id)).toEqual([SETUP_ID, OTHER_SETUP_ID]);
    expect(rows.map((row) => row.character_id)).toEqual([CHARACTER_ID, CHARACTER_ID]);
    expect(typeof rows[0].id).toBe("string");
    expect(typeof rows[0].character_id).toBe("string");
    expect(rows[0].id).toBe(SETUP_ID);
    expect(rows[0].character_id).toBe(CHARACTER_ID);
  });

  it("addresses the character id verbatim, without parsing it — DoD-1", async () => {
    const mock = serve({ setups: [] });
    await fetchSetups(CHARACTER_ID, false);
    expect(seen(mock)[0].path).toBe(`/api/characters/${CHARACTER_ID}/setups`);
  });
});

// ---------------------------------------------------------------------------
describe("createSetup", () => {
  it("POSTs /api/characters/<id>/setups with the JSON body { name, description } — DoD-2", async () => {
    const mock = serve(TAVERN, 201);
    await expect(
      createSetup(CHARACTER_ID, { name: TAVERN.name, description: TAVERN.description }),
    ).resolves.toEqual(TAVERN);
    expect(seen(mock)).toEqual([{ method: "POST", path: COLLECTION_PATH, search: "" }]);
    expect(sentBody(mock)).toEqual({ name: TAVERN.name, description: TAVERN.description });
    expect(bodyKeys(mock).sort()).toEqual(["description", "name"]);
  });

  it("sends an empty description as an empty string, not as an absent key — DoD-2", async () => {
    const mock = serve({ ...TAVERN, description: "" }, 201);
    await createSetup(CHARACTER_ID, { name: TAVERN.name, description: "" });
    expect(sentBody(mock)).toEqual({ name: TAVERN.name, description: "" });
    expect(bodyKeys(mock).sort()).toEqual(["description", "name"]);
  });
});

// ---------------------------------------------------------------------------
describe("updateSetup", () => {
  it("PATCHes /api/setups/<id> with only the name it was given — DoD-2", async () => {
    const renamed: Setup = { ...TAVERN, name: "The Gilded Cage" };
    const mock = serve(renamed);
    await expect(updateSetup(SETUP_ID, { name: "The Gilded Cage" })).resolves.toEqual(renamed);
    expect(seen(mock)).toEqual([{ method: "PATCH", path: SETUP_PATH, search: "" }]);
    expect(bodyKeys(mock)).toEqual(["name"]);
    expect(sentBody(mock)).toEqual({ name: "The Gilded Cage" });
  });

  it("PATCHes /api/setups/<id> with only the description it was given — DoD-2", async () => {
    const edited: Setup = { ...TAVERN, description: "# The Gilded Tavern\n\nThe debt is paid." };
    const mock = serve(edited);
    await expect(updateSetup(SETUP_ID, { description: edited.description })).resolves.toEqual(
      edited,
    );
    expect(seen(mock)).toEqual([{ method: "PATCH", path: SETUP_PATH, search: "" }]);
    expect(bodyKeys(mock)).toEqual(["description"]);
    expect(sentBody(mock)).toEqual({ description: edited.description });
  });

  it("PATCHes both keys when both are given — DoD-2", async () => {
    const edited: Setup = { ...TAVERN, name: "The Cage", description: "# The Cage\n\nQuiet." };
    const mock = serve(edited);
    await expect(
      updateSetup(SETUP_ID, { name: edited.name, description: edited.description }),
    ).resolves.toEqual(edited);
    expect(bodyKeys(mock).sort()).toEqual(["description", "name"]);
    expect(sentBody(mock)).toEqual({ name: edited.name, description: edited.description });
  });

  it("sends no key at all for an empty patch — DoD-2", async () => {
    const mock = serve(TAVERN);
    await expect(updateSetup(SETUP_ID, {})).resolves.toEqual(TAVERN);
    expect(bodyKeys(mock)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("the two action calls", () => {
  it("archiveSetup POSTs /api/setups/<id>/archive and resolves to the response's setup — DoD-2", async () => {
    const archived: Setup = { ...TAVERN, archived_at: "2026-03-21T07:00:00.000000+00:00" };
    const mock = serve(archived);
    await expect(archiveSetup(SETUP_ID)).resolves.toEqual(archived);
    expect(seen(mock)).toEqual([
      { method: "POST", path: `${SETUP_PATH}/archive`, search: "" },
    ]);
  });

  it("restoreSetup POSTs /api/setups/<id>/restore and resolves to the response's setup — DoD-2", async () => {
    const mock = serve(TAVERN);
    await expect(restoreSetup(SETUP_ID)).resolves.toEqual(TAVERN);
    expect(seen(mock)).toEqual([
      { method: "POST", path: `${SETUP_PATH}/restore`, search: "" },
    ]);
  });

  it("an id beyond MAX_SAFE_INTEGER reaches every id-addressed route unchanged — DoD-2", async () => {
    for (const call of [
      () => updateSetup(SETUP_ID, { name: "x" }),
      () => archiveSetup(SETUP_ID),
      () => restoreSetup(SETUP_ID),
    ]) {
      const mock = serve(TAVERN);
      await call();
      expect(seen(mock)[0].path.startsWith(`/api/setups/${SETUP_ID}`)).toBe(true);
      vi.unstubAllGlobals();
    }
  });
});

// ---------------------------------------------------------------------------
describe("failures are the shared client's ApiErrors", () => {
  it("a 404 setup_not_found envelope rejects archiveSetup with that ApiError code — DoD-3", async () => {
    serve(envelope("setup_not_found", "That setup does not exist."), 404);
    const error = await rejection(() => archiveSetup(SETUP_ID));
    expect(isApiError(error)).toBe(true);
    expect(isApiError(error) ? error.code : null).toBe("setup_not_found");
    expect(isApiError(error) ? error.status : null).toBe(404);
  });

  it("the same 404 rejects the other id-addressed calls with setup_not_found — DoD-3", async () => {
    for (const call of [
      () => updateSetup(SETUP_ID, { name: "x" }),
      () => restoreSetup(SETUP_ID),
    ]) {
      serve(envelope("setup_not_found", "That setup does not exist."), 404);
      const error = await rejection(call);
      expect(isApiError(error)).toBe(true);
      expect(isApiError(error) ? error.code : null).toBe("setup_not_found");
      vi.unstubAllGlobals();
    }
  });

  it("a 404 character_not_found envelope rejects the collection calls with that code — DoD-3", async () => {
    for (const call of [
      () => fetchSetups(CHARACTER_ID, false),
      () => createSetup(CHARACTER_ID, { name: "x", description: "" }),
    ]) {
      serve(envelope("character_not_found", "That character does not exist."), 404);
      const error = await rejection(call);
      expect(isApiError(error)).toBe(true);
      expect(isApiError(error) ? error.code : null).toBe("character_not_found");
      vi.unstubAllGlobals();
    }
  });
});

// ---------------------------------------------------------------------------
describe("isSetupArchived", () => {
  it("is true when archived_at is a string — DoD-3", () => {
    expect(isSetupArchived(HARBOUR)).toBe(true);
  });

  it("is false when archived_at is null — DoD-3", () => {
    expect(isSetupArchived(TAVERN)).toBe(false);
  });
});
