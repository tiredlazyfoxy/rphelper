// Feature 029, step 005 (DoD-1..12) — `SearchScreen`: the box, the five groups in UC-059
// order, the archived / disabled markings, the per-kind targets and the inline blank /
// failure states. DoD-1..DoD-10 live here; DoD-11 and DoD-12 are in tests/app/App.test.tsx.
// DoD-13 is [manual/live] and carries no test.
//
// Every expected value comes from the plan, never from the component: `context.md`'s Literals
// table (the five group headings, the four memo level labels, "Archived", "Disabled",
// "Nothing found.", "Search failed", "Retry", the box's accessible name "Search query"), U1
// (an embedding failure fails the whole search, inline, no toast), U3 (archived rows are
// included and marked), U4 and D7 (row content, plain-text snippets), D9 (focus on every
// arrival at `/search`), and `004.context.md`'s "Targets" table. The component's module
// constants are private, so every assertion binds to a role, an accessible name or one of
// those literal strings through the rendered DOM.
//
// Binding: `SearchScreen` takes **no props** (it owns its own `SearchState`), so each render
// is `<SearchScreen />` inside `<AppProviders>` then `<MemoryRouter>`, with a `useLocation`
// probe reading `pathname + search`. Ids are strings throughout.
//
// Feature 034, step 004 (S034_004_DoD7): a session row's primary text and an entry row's
// session text are now the session LABEL — the stored name, else the local `YYYY-MM-DD` of the
// start with no time (DEC-034-9, US-150.AC-1/AC-2, US-152.AC-2). The 029 DoD-5 clauses below
// assert that rule for never-renamed hits (name / session_name null). The local date is never
// pinned to a literal: `localDate` below computes it with Intl in the runtime's own zone, an
// oracle independent of the component and of `sessionLabel` (exact zone values are asserted
// only in tests/app/sessionLabel.test.ts).
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SearchScreen } from "../../src/app/SearchScreen";
import type {
  CharacterHit,
  EntryHit,
  MemoHit,
  MySearchResults,
  SessionHit,
  SetupHit,
} from "../../src/app/searchApi";
import { AppProviders } from "../../src/shared/AppProviders";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Seen = { method: string; path: string; q: string | null };
type User = ReturnType<typeof userEvent.setup>;

// ----------------------------------------------------------------- the literals
const SEARCH_PATH = "/search";
const API_PATH = "/api/search";
const QUERY_PARAM = "q";
const BOX_NAME = "Search query";
/** The five group headings, which are also the five regions' accessible names, in order. */
const GROUP_NAMES = ["Characters", "Setups", "Sessions", "Entries", "Notes"] as const;
const ARCHIVED_BADGE = "Archived";
const DISABLED_BADGE = "Disabled";
/** A space, U+00B7, a space — the secondary line's separator (DoD-5). */
const SEPARATOR = " · ";
const NO_HITS_TEXT = "Nothing found.";
const FAILURE_HEADING = "Search failed";
const RETRY_NAME = /^retry$/i;
const USER_NOTE = "User note";
const CHARACTER_NOTE = "Character note";
const SETUP_NOTE = "Setup note";
const SESSION_NOTE = "Session note";

// ------------------------------------------------------------------- the ids
// Decimal digit strings past Number.MAX_SAFE_INTEGER, so a coerced id would show in the href.
const CHARACTER_ID = "7250000000000000011";
const ARCHIVED_CHARACTER_ID = "7250000000000000012";
const KAEL_CHARACTER_ID = "7250000000000000013";
const SETUP_ID = "7250000000000000021";
const SETUP_HOST_ID = "7250000000000000022";
const ARCHIVED_SETUP_ID = "7250000000000000023";
const SESSION_ID = "7250000000000000031";
const ARCHIVED_SESSION_ID = "7250000000000000032";
const SOLO_SESSION_ID = "7250000000000000033";
const ENTRY_ID = "7250000000000000041";
const ENTRY_SESSION_ID = "7250000000000000042";
const USER_MEMO_ID = "7250000000000000051";
const CHARACTER_MEMO_ID = "7250000000000000052";
const CHARACTER_MEMO_CHARACTER_ID = "7250000000000000053";
const SETUP_MEMO_ID = "7250000000000000054";
const SETUP_MEMO_SETUP_ID = "7250000000000000055";
const SETUP_MEMO_CHARACTER_ID = "7250000000000000056";
const SESSION_MEMO_ID = "7250000000000000057";
const SESSION_MEMO_SESSION_ID = "7250000000000000058";

// --------------------------------------------------------------- the timestamps
const SESSION_STAMP = "2026-05-09T08:00:00.000000+00:00";
const OTHER_STAMP = "2026-05-10T09:30:00.000000+00:00";
const ENTRY_STAMP = "2026-05-11T19:45:00.000000+00:00";
/** Reads one Intl part of `instant` in the runtime's own zone. */
function localPart(parts: Intl.DateTimeFormatPart[], type: Intl.DateTimeFormatPartTypes): string {
  return parts.find((part) => part.type === type)?.value ?? "";
}

/**
 * The local `YYYY-MM-DD` of `instant` in the runtime's zone — the expected label of a
 * never-renamed session (S034_004_DoD7). Built with Intl directly, not with the module under
 * test, so the suite passes in any zone without trusting the code it checks.
 */
function localDate(instant: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(instant));
  return `${localPart(parts, "year")}-${localPart(parts, "month")}-${localPart(parts, "day")}`;
}

/** The local `HH:MM` (24-hour) of `instant` — used only to assert that NO time is shown. */
function localTime(instant: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(instant));
  return `${localPart(parts, "hour")}:${localPart(parts, "minute")}`;
}

/** 034: a never-renamed session's label is its local start date, with no time. */
const SESSION_START = localDate(SESSION_STAMP);
const OTHER_START = localDate(OTHER_STAMP);
const ENTRY_START = localDate(ENTRY_STAMP);

// ------------------------------------------------------------------- the hits
const CHARACTER_HIT: CharacterHit = { id: CHARACTER_ID, name: "Mira Vane", archived: false };
const ARCHIVED_CHARACTER_HIT: CharacterHit = {
  id: ARCHIVED_CHARACTER_ID,
  name: "Mira Hollow",
  archived: true,
};
const KAEL_CHARACTER_HIT: CharacterHit = { id: KAEL_CHARACTER_ID, name: "Kael Rook", archived: false };

const SETUP_HIT: SetupHit = {
  id: SETUP_ID,
  name: "Harbour nights",
  character_id: SETUP_HOST_ID,
  character_name: "Corvin Hale",
  archived: false,
};
const ARCHIVED_SETUP_HIT: SetupHit = {
  id: ARCHIVED_SETUP_ID,
  name: "Harbour dawns",
  character_id: SETUP_HOST_ID,
  character_name: "Corvin Hale",
  archived: true,
};

const SESSION_HIT: SessionHit = {
  id: SESSION_ID,
  character_name: "Mirabel Ash",
  setup_name: "Harbour nights",
  name: null,
  created_at: SESSION_STAMP,
  archived: false,
};
/** No setup: the secondary line is the character name alone (DoD-5). */
const SOLO_SESSION_HIT: SessionHit = {
  id: SOLO_SESSION_ID,
  character_name: "Perrin Vale",
  setup_name: null,
  name: null,
  created_at: OTHER_STAMP,
  archived: false,
};
const ARCHIVED_SESSION_HIT: SessionHit = {
  id: ARCHIVED_SESSION_ID,
  character_name: "Yewen Marsh",
  setup_name: null,
  name: null,
  created_at: OTHER_STAMP,
  archived: true,
};

/** The snippet holds literal markdown: D7 renders snippets as plain text. */
const ENTRY_HIT: EntryHit = {
  id: ENTRY_ID,
  session_id: ENTRY_SESSION_ID,
  snippet: "A **bold** cut of the reply",
  character_name: "Tamsin Reed",
  session_name: null,
  session_created_at: ENTRY_STAMP,
};

const USER_MEMO_HIT: MemoHit = {
  id: USER_MEMO_ID,
  scope: "user",
  scope_id: null,
  character_id: null,
  snippet: "Write shorter replies",
  is_enabled: true,
};
const CHARACTER_MEMO_HIT: MemoHit = {
  id: CHARACTER_MEMO_ID,
  scope: "character",
  scope_id: CHARACTER_MEMO_CHARACTER_ID,
  character_id: CHARACTER_MEMO_CHARACTER_ID,
  snippet: "Mira keeps a ledger of debts",
  is_enabled: true,
};
/** The disabled note of DoD-3, and the setup-level note of DoD-6. */
const DISABLED_SETUP_MEMO_HIT: MemoHit = {
  id: SETUP_MEMO_ID,
  scope: "setup",
  scope_id: SETUP_MEMO_SETUP_ID,
  character_id: SETUP_MEMO_CHARACTER_ID,
  snippet: "The harbour watch is bribable",
  is_enabled: false,
};
const SESSION_MEMO_HIT: MemoHit = {
  id: SESSION_MEMO_ID,
  scope: "session",
  scope_id: SESSION_MEMO_SESSION_ID,
  character_id: null,
  snippet: "The watch changes at dawn",
  is_enabled: true,
};

// --------------------------------------------------------------- the payloads
function noHits(): MySearchResults {
  return { characters: [], setups: [], sessions: [], entries: [], memos: [] };
}

function results(groups: Partial<MySearchResults>): MySearchResults {
  return { ...noHits(), ...groups };
}

const ONE_PER_KIND: MySearchResults = results({
  characters: [CHARACTER_HIT],
  setups: [SETUP_HIT],
  sessions: [SESSION_HIT],
  entries: [ENTRY_HIT],
  memos: [DISABLED_SETUP_MEMO_HIT],
});

const FAILURE_MESSAGE = "No embedding model is designated.";
const FAILURE_ENVELOPE = {
  error: { code: "no_embedding_model", message: FAILURE_MESSAGE, detail: {} },
};

// ------------------------------------------------------------------ the stub
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

/** `fetch`, routed by the exact pathname `/api/search`; anything else answers 404. */
function stubSearch(answer: (query: string) => Response) {
  const calls: Seen[] = [];
  const mock = vi.fn<FetchFn>(async (input, init) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, "http://localhost");
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    const query = url.searchParams.get(QUERY_PARAM);
    calls.push({ method, path: url.pathname, q: query });
    if (method === "GET" && url.pathname === API_PATH) {
      return answer(query ?? "");
    }
    return jsonResponse({ error: { code: "not_found", message: "", detail: {} } }, 404);
  });
  vi.stubGlobal("fetch", mock);
  return { calls };
}

/** One fixed 200 answer for every query. */
function serve(payload: MySearchResults) {
  return stubSearch(() => jsonResponse(payload, 200));
}

function searchRequests(calls: Seen[]): Seen[] {
  return calls.filter((call) => call.method === "GET" && call.path === API_PATH);
}

// ----------------------------------------------------------------- the render
const HOST = "search-host";

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="probe-location">{`${location.pathname}${location.search}`}</output>;
}

/** A second way onto `/search`, so DoD-10 can arrive there twice without a remount. */
function GoSearchProbe() {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => void navigate(SEARCH_PATH)}>
      probe go search
    </button>
  );
}

/**
 * The screen alone at `initialPath`, inside a host div so every scoped query ignores the
 * probes beside it. The `*` route catches each target the rows navigate to.
 */
function renderScreen(initialPath: string = SEARCH_PATH) {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <div data-testid={HOST}>
          <Routes>
            <Route path={SEARCH_PATH} element={<SearchScreen />} />
            <Route path="*" element={<p>elsewhere</p>} />
          </Routes>
        </div>
        <LocationProbe />
        <GoSearchProbe />
        <button type="button">probe focus sink</button>
      </MemoryRouter>
    </AppProviders>,
  );
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

// ---------------------------------------------------------------- the queries
function host(): HTMLElement {
  return screen.getByTestId(HOST);
}

function page() {
  return within(host());
}

function currentHref(): string {
  return screen.getByTestId("probe-location").textContent ?? "";
}

function searchBox(): HTMLElement {
  return page().getByRole("textbox", { name: BOX_NAME });
}

function queryRegions(): HTMLElement[] {
  return page().queryAllByRole("region");
}

function group(name: string): HTMLElement {
  return page().getByRole("region", { name });
}

/** The row whose text holds `text`: each row is a link to its target. */
function rowLink(region: HTMLElement, text: string): HTMLElement {
  const found = within(region)
    .getAllByRole("link")
    .find((link) => (link.textContent ?? "").includes(text));
  if (found === undefined) throw new Error(`no row link holding "${text}"`);
  return found;
}

/** A row's whole block — the list item, so a badge rendered beside the link is in scope. */
function rowBlock(region: HTMLElement, text: string): HTMLElement {
  const link = rowLink(region, text);
  return link.closest("li") ?? link.parentElement ?? link;
}

/** Whether `element` or an ancestor up to `bound` carries an inline line-through. */
function isStruckThrough(element: HTMLElement, bound: HTMLElement): boolean {
  let node: HTMLElement | null = element;
  while (node !== null) {
    const decoration = `${node.style.textDecoration} ${node.style.textDecorationLine}`;
    if (decoration.includes("line-through")) return true;
    if (node === bound) return false;
    node = node.parentElement;
  }
  return false;
}

function notifications(): Element[] {
  return Array.from(document.querySelectorAll(".mantine-Notification-root"));
}

// ---------------------------------------------------------------------------
describe("029 step 005 — one query reaches every kind, grouped in UC-059 order (US-074.AC-1, US-075.AC-1)", () => {
  it("at /search?q=mira five regions named Characters, Setups, Sessions, Entries, Notes render in that order, each holding its hit, from one request carrying q=mira — DoD-1", async () => {
    const { calls } = serve(ONE_PER_KIND);
    renderScreen(`${SEARCH_PATH}?q=mira`);
    await flush();

    expect(await page().findByRole("region", { name: GROUP_NAMES[0] })).toBeInTheDocument();
    expect(queryRegions()).toEqual(GROUP_NAMES.map((name) => group(name)));

    expect(within(group("Characters")).getByText(CHARACTER_HIT.name)).toBeInTheDocument();
    expect(within(group("Setups")).getByText(SETUP_HIT.name)).toBeInTheDocument();
    expect(within(group("Sessions")).getByText(SESSION_START)).toBeInTheDocument();
    expect(within(group("Entries")).getByText(ENTRY_HIT.snippet)).toBeInTheDocument();
    expect(within(group("Notes")).getByText(DISABLED_SETUP_MEMO_HIT.snippet)).toBeInTheDocument();

    expect(searchRequests(calls).map((call) => call.q)).toEqual(["mira"]);
  });
});

// ---------------------------------------------------------------------------
describe("029 step 005 — a group with no hits is not rendered (US-075.AC-1)", () => {
  it("with hits only in Sessions and Notes exactly those two regions render, Sessions before Notes — DoD-2", async () => {
    serve(results({ sessions: [SESSION_HIT], memos: [USER_MEMO_HIT] }));
    renderScreen(`${SEARCH_PATH}?q=mira`);
    await flush();

    expect(await page().findByRole("region", { name: "Sessions" })).toBeInTheDocument();
    // The positive half first — the two groups are really there — then the exact set and order.
    expect(within(group("Sessions")).getByText(SESSION_START)).toBeInTheDocument();
    expect(within(group("Notes")).getByText(USER_MEMO_HIT.snippet)).toBeInTheDocument();
    expect(queryRegions()).toEqual([group("Sessions"), group("Notes")]);
  });

  it("with five empty groups the page reads Nothing found. and renders no region at all — DoD-2", async () => {
    serve(noHits());
    renderScreen(`${SEARCH_PATH}?q=mira`);
    await flush();

    // The positive half — the empty state's own text — keeps the absence from passing vacuously.
    expect(await page().findByText(NO_HITS_TEXT)).toBeInTheDocument();
    expect(queryRegions()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("029 step 005 — a disabled note is shown as disabled (US-137.AC-2, D7, US-119)", () => {
  it("of two note hits only the is_enabled false one carries a Disabled badge and a struck-through snippet, and each row names its level — DoD-3", async () => {
    serve(results({ memos: [DISABLED_SETUP_MEMO_HIT, USER_MEMO_HIT] }));
    renderScreen(`${SEARCH_PATH}?q=harbour`);
    await flush();

    const notes = await page().findByRole("region", { name: "Notes" });
    const disabled = rowBlock(notes, DISABLED_SETUP_MEMO_HIT.snippet);
    const enabled = rowBlock(notes, USER_MEMO_HIT.snippet);

    expect(within(disabled).getByText(DISABLED_BADGE)).toBeInTheDocument();
    expect(within(enabled).queryByText(DISABLED_BADGE)).toBeNull();

    expect(
      isStruckThrough(within(disabled).getByText(DISABLED_SETUP_MEMO_HIT.snippet), disabled),
    ).toBe(true);
    expect(isStruckThrough(within(enabled).getByText(USER_MEMO_HIT.snippet), enabled)).toBe(false);

    expect(within(disabled).getByText(SETUP_NOTE)).toBeInTheDocument();
    expect(within(enabled).getByText(USER_NOTE)).toBeInTheDocument();
  });

  it("a character note and a session note name their own levels too — DoD-3", async () => {
    serve(results({ memos: [CHARACTER_MEMO_HIT, SESSION_MEMO_HIT] }));
    renderScreen(`${SEARCH_PATH}?q=mira`);
    await flush();

    const notes = await page().findByRole("region", { name: "Notes" });
    expect(
      within(rowBlock(notes, CHARACTER_MEMO_HIT.snippet)).getByText(CHARACTER_NOTE),
    ).toBeInTheDocument();
    expect(
      within(rowBlock(notes, SESSION_MEMO_HIT.snippet)).getByText(SESSION_NOTE),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
describe("029 step 005 — archived rows are included and marked (U3, D7)", () => {
  it("an archived character, setup and session each carry an Archived badge and their live siblings carry none — DoD-4", async () => {
    serve(
      results({
        characters: [CHARACTER_HIT, ARCHIVED_CHARACTER_HIT],
        setups: [SETUP_HIT, ARCHIVED_SETUP_HIT],
        sessions: [SESSION_HIT, ARCHIVED_SESSION_HIT],
      }),
    );
    renderScreen(`${SEARCH_PATH}?q=mira`);
    await flush();
    await page().findByRole("region", { name: "Characters" });

    const marked: Array<[string, string]> = [
      ["Characters", ARCHIVED_CHARACTER_HIT.name],
      ["Setups", ARCHIVED_SETUP_HIT.name],
      ["Sessions", ARCHIVED_SESSION_HIT.character_name],
    ];
    const unmarked: Array<[string, string]> = [
      ["Characters", CHARACTER_HIT.name],
      ["Setups", SETUP_HIT.name],
      ["Sessions", SESSION_HIT.character_name],
    ];

    for (const [groupName, rowText] of marked) {
      expect(within(rowBlock(group(groupName), rowText)).getByText(ARCHIVED_BADGE)).toBeInTheDocument();
    }
    for (const [groupName, rowText] of unmarked) {
      expect(within(rowBlock(group(groupName), rowText)).queryByText(ARCHIVED_BADGE)).toBeNull();
    }
  });
});

// ---------------------------------------------------------------------------
describe("029 step 005 — what each row says (D4, D7)", () => {
  const PAYLOAD = results({
    setups: [SETUP_HIT],
    sessions: [SESSION_HIT, SOLO_SESSION_HIT],
    entries: [ENTRY_HIT],
  });

  it("the setup row shows the setup's name and its character's name — DoD-5", async () => {
    serve(PAYLOAD);
    renderScreen(`${SEARCH_PATH}?q=harbour`);
    await flush();

    const row = rowBlock(await page().findByRole("region", { name: "Setups" }), SETUP_HIT.name);
    expect(within(row).getByText(SETUP_HIT.name)).toBeInTheDocument();
    expect(within(row).getByText(SETUP_HIT.character_name)).toBeInTheDocument();
  });

  it("the session row shows its label (local start date for a null name) and <character> · <setup>, and only the character when setup_name is null — DoD-5, S034_004_DoD7", async () => {
    serve(PAYLOAD);
    renderScreen(`${SEARCH_PATH}?q=harbour`);
    await flush();

    const sessions = await page().findByRole("region", { name: "Sessions" });

    const withSetup = rowBlock(sessions, SESSION_HIT.character_name);
    expect(within(withSetup).getByText(SESSION_START)).toBeInTheDocument();
    expect(
      within(withSetup).getByText(`${SESSION_HIT.character_name}${SEPARATOR}${SESSION_HIT.setup_name}`),
    ).toBeInTheDocument();

    const withoutSetup = rowBlock(sessions, SOLO_SESSION_HIT.character_name);
    expect(within(withoutSetup).getByText(OTHER_START)).toBeInTheDocument();
    expect(within(withoutSetup).getByText(SOLO_SESSION_HIT.character_name)).toBeInTheDocument();
    expect(withoutSetup.textContent ?? "").not.toContain("·");
  });

  it("the entry row shows its snippet and <character> · <session label> (local start date for a null session_name) — DoD-5, S034_004_DoD7", async () => {
    serve(PAYLOAD);
    renderScreen(`${SEARCH_PATH}?q=harbour`);
    await flush();

    const row = rowBlock(await page().findByRole("region", { name: "Entries" }), ENTRY_HIT.snippet);
    expect(within(row).getByText(ENTRY_HIT.snippet)).toBeInTheDocument();
    expect(
      within(row).getByText(`${ENTRY_HIT.character_name}${SEPARATOR}${ENTRY_START}`),
    ).toBeInTheDocument();
  });

  it("a snippet holding **bold** renders literally, with no markdown element in the row — DoD-5", async () => {
    serve(PAYLOAD);
    renderScreen(`${SEARCH_PATH}?q=harbour`);
    await flush();

    const row = rowBlock(await page().findByRole("region", { name: "Entries" }), ENTRY_HIT.snippet);
    expect(within(row).getByText("A **bold** cut of the reply")).toBeInTheDocument();
    expect(row.querySelector("strong")).toBeNull();
    expect(row.querySelector("em")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// The targets are 004.context.md's "Targets" table, verbatim.
type TargetCase = {
  kind: string;
  payload: MySearchResults;
  group: string;
  rowText: string;
  target: string;
};

const TARGET_CASES: TargetCase[] = [
  {
    kind: "a character",
    payload: results({ characters: [CHARACTER_HIT] }),
    group: "Characters",
    rowText: CHARACTER_HIT.name,
    target: `/characters/${CHARACTER_ID}`,
  },
  {
    kind: "a setup",
    payload: results({ setups: [SETUP_HIT] }),
    group: "Setups",
    rowText: SETUP_HIT.name,
    target: `/characters/${SETUP_HOST_ID}`,
  },
  {
    kind: "a session",
    payload: results({ sessions: [SESSION_HIT] }),
    group: "Sessions",
    rowText: SESSION_HIT.character_name,
    target: `/sessions/${SESSION_ID}`,
  },
  {
    kind: "an entry",
    payload: results({ entries: [ENTRY_HIT] }),
    group: "Entries",
    rowText: ENTRY_HIT.snippet,
    target: `/sessions/${ENTRY_SESSION_ID}?entry=${ENTRY_ID}`,
  },
  {
    kind: "a user note",
    payload: results({ memos: [USER_MEMO_HIT] }),
    group: "Notes",
    rowText: USER_MEMO_HIT.snippet,
    target: "/settings",
  },
  {
    kind: "a character note",
    payload: results({ memos: [CHARACTER_MEMO_HIT] }),
    group: "Notes",
    rowText: CHARACTER_MEMO_HIT.snippet,
    target: `/characters/${CHARACTER_MEMO_CHARACTER_ID}`,
  },
  {
    kind: "a setup note",
    payload: results({ memos: [DISABLED_SETUP_MEMO_HIT] }),
    group: "Notes",
    rowText: DISABLED_SETUP_MEMO_HIT.snippet,
    target: `/characters/${SETUP_MEMO_CHARACTER_ID}`,
  },
  {
    kind: "a session note",
    payload: results({ memos: [SESSION_MEMO_HIT] }),
    group: "Notes",
    rowText: SESSION_MEMO_HIT.snippet,
    target: `/sessions/${SESSION_MEMO_SESSION_ID}?notes=open`,
  },
];

describe("029 step 005 — a result lands on what it names (UC-060, U4)", () => {
  it.each(TARGET_CASES)(
    "clicking the row for $kind moves the in-entry router to $target — DoD-6",
    async (testCase) => {
      const user = newUser();
      serve(testCase.payload);
      renderScreen(`${SEARCH_PATH}?q=mira`);
      await flush();

      const link = rowLink(await page().findByRole("region", { name: testCase.group }), testCase.rowText);
      expect(link).toHaveAttribute("href", testCase.target);

      await user.click(link);
      await flush();

      expect(currentHref()).toBe(testCase.target);
    },
  );
});

// ---------------------------------------------------------------------------
describe("029 step 005 — a blank query shows nothing and asks nothing (D1, U4)", () => {
  const BLANK_CASES: Array<[string, string]> = [
    [SEARCH_PATH, ""],
    [`${SEARCH_PATH}?q=%20`, " "],
  ];

  it.each(BLANK_CASES)(
    "at %s the box renders holding %j, with no region, no Nothing found. and no /api/search request — DoD-7",
    async (path, value) => {
      // The stub would answer a hit in every group, so a request would be plainly visible.
      const { calls } = serve(ONE_PER_KIND);
      renderScreen(path);
      await flush();

      // The positive half: the box is there and carries the URL's query, blank or spaces.
      expect(searchBox()).toHaveValue(value);
      expect(queryRegions()).toEqual([]);
      expect(page().queryByText(NO_HITS_TEXT)).toBeNull();
      expect(searchRequests(calls)).toEqual([]);
    },
  );
});

// ---------------------------------------------------------------------------
describe("029 step 005 — the box follows the URL and submits to it (U4)", () => {
  it("at /search?q=mira the box holds mira; typing kael and pressing Enter navigates to /search?q=kael, requests kael and shows its results — DoD-8", async () => {
    const user = newUser();
    const { calls } = stubSearch((query) =>
      jsonResponse(
        query === "kael"
          ? results({ characters: [KAEL_CHARACTER_HIT] })
          : results({ characters: [CHARACTER_HIT] }),
        200,
      ),
    );
    renderScreen(`${SEARCH_PATH}?q=mira`);
    await flush();

    expect(searchBox()).toHaveValue("mira");
    expect(
      within(await page().findByRole("region", { name: "Characters" })).getByText(CHARACTER_HIT.name),
    ).toBeInTheDocument();

    await user.clear(searchBox());
    await user.type(searchBox(), "kael{Enter}");
    await flush();

    expect(currentHref()).toBe(`${SEARCH_PATH}?q=kael`);
    expect(searchRequests(calls).map((call) => call.q)).toEqual(["mira", "kael"]);
    expect(within(group("Characters")).getByText(KAEL_CHARACTER_HIT.name)).toBeInTheDocument();
    expect(page().queryByText(CHARACTER_HIT.name)).toBeNull();
    expect(searchBox()).toHaveValue("kael");
  });
});

// ---------------------------------------------------------------------------
describe("029 step 005 — an embedding failure fails the whole page, inline (U1)", () => {
  it("a 409 no_embedding_model answer renders Search failed with the envelope's message, no region and no notification; Retry re-requests the same q and a 200 shows the groups — DoD-9", async () => {
    const user = newUser();
    let answered = 0;
    const { calls } = stubSearch(() => {
      answered += 1;
      return answered === 1 ? jsonResponse(FAILURE_ENVELOPE, 409) : jsonResponse(ONE_PER_KIND, 200);
    });
    renderScreen(`${SEARCH_PATH}?q=mira`);
    await flush();

    // Both positive halves: the heading and the envelope's own message.
    expect(await page().findByText(FAILURE_HEADING)).toBeInTheDocument();
    expect(page().getByText(FAILURE_MESSAGE)).toBeInTheDocument();
    expect(queryRegions()).toEqual([]);
    expect(notifications()).toEqual([]);

    await user.click(page().getByRole("button", { name: RETRY_NAME }));
    await flush();

    expect(searchRequests(calls).map((call) => call.q)).toEqual(["mira", "mira"]);
    expect(queryRegions()).toEqual(GROUP_NAMES.map((name) => group(name)));
    expect(page().queryByText(FAILURE_HEADING)).toBeNull();
    expect(notifications()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("029 step 005 — the box is focused on every arrival at /search (D9)", () => {
  it("rendering at /search focuses the box, and after focus moves away a fresh navigation to the same path focuses it again — DoD-10", async () => {
    const user = newUser();
    serve(noHits());
    renderScreen(SEARCH_PATH);
    await flush();

    expect(searchBox()).toHaveFocus();

    await user.click(screen.getByRole("button", { name: /^probe focus sink$/i }));
    await flush();
    expect(searchBox()).not.toHaveFocus();

    // A second navigation to `/search` — same path, new location key — not a remount.
    await user.click(screen.getByRole("button", { name: /^probe go search$/i }));
    await flush();

    expect(currentHref()).toBe(SEARCH_PATH);
    expect(searchBox()).toHaveFocus();
  });
});

// ===========================================================================
// Feature 034, step 004 — S034_004_DoD7 on my-search: a renamed session's session row and
// entry row show its name; a never-renamed one shows its local start date with no time
// (US-150.AC-1, US-150.AC-2, US-152.AC-2; DEC-034-8, DEC-034-9).
// ===========================================================================
describe("034 step 004 — my-search rows show the session label", () => {
  /** A renamed session whose name looks like nothing date-ish. */
  const NAMED_SESSION_HIT: SessionHit = { ...SESSION_HIT, name: "Harbour at dusk" };
  /** A renamed session whose name looks like a date — it is still shown verbatim. */
  const DATE_NAMED_SESSION_HIT: SessionHit = { ...SOLO_SESSION_HIT, name: "1999-12-31" };
  /** An entry of a renamed session. */
  const NAMED_ENTRY_HIT: EntryHit = { ...ENTRY_HIT, session_name: "Harbour at dusk" };

  it("a renamed session's row shows its name and not its start date — S034_004_DoD7", async () => {
    serve(results({ sessions: [NAMED_SESSION_HIT] }));
    renderScreen(`${SEARCH_PATH}?q=harbour`);
    await flush();

    const sessions = await page().findByRole("region", { name: "Sessions" });
    const row = rowBlock(sessions, NAMED_SESSION_HIT.character_name);
    expect(within(row).getByText("Harbour at dusk")).toBeInTheDocument();
    expect(row.textContent ?? "").not.toContain(SESSION_START);
    expect(row.textContent ?? "").not.toContain(localTime(SESSION_STAMP));
  });

  it("a name that looks like a date is shown verbatim in place of the start date — S034_004_DoD7", async () => {
    serve(results({ sessions: [DATE_NAMED_SESSION_HIT] }));
    renderScreen(`${SEARCH_PATH}?q=1999`);
    await flush();

    const sessions = await page().findByRole("region", { name: "Sessions" });
    const row = rowBlock(sessions, DATE_NAMED_SESSION_HIT.character_name);
    expect(within(row).getByText("1999-12-31")).toBeInTheDocument();
    expect(row.textContent ?? "").not.toContain(OTHER_START);
  });

  it("a never-renamed session's row shows its local start date with no time — S034_004_DoD7", async () => {
    serve(results({ sessions: [SESSION_HIT] }));
    renderScreen(`${SEARCH_PATH}?q=harbour`);
    await flush();

    const sessions = await page().findByRole("region", { name: "Sessions" });
    const row = rowBlock(sessions, SESSION_HIT.character_name);
    expect(within(row).getByText(SESSION_START)).toBeInTheDocument();
    expect(row.textContent ?? "").not.toContain(localTime(SESSION_STAMP));
    expect(row.textContent ?? "").not.toMatch(/\d{2}:\d{2}/);
  });

  it("a renamed and a never-renamed session side by side each show their own label — S034_004_DoD7", async () => {
    serve(results({ sessions: [NAMED_SESSION_HIT, SOLO_SESSION_HIT] }));
    renderScreen(`${SEARCH_PATH}?q=harbour`);
    await flush();

    const sessions = await page().findByRole("region", { name: "Sessions" });
    expect(
      within(rowBlock(sessions, NAMED_SESSION_HIT.character_name)).getByText("Harbour at dusk"),
    ).toBeInTheDocument();
    expect(
      within(rowBlock(sessions, SOLO_SESSION_HIT.character_name)).getByText(OTHER_START),
    ).toBeInTheDocument();
  });

  it("an entry of a renamed session shows <character> · <name> — S034_004_DoD7", async () => {
    serve(results({ entries: [NAMED_ENTRY_HIT] }));
    renderScreen(`${SEARCH_PATH}?q=bold`);
    await flush();

    const row = rowBlock(await page().findByRole("region", { name: "Entries" }), ENTRY_HIT.snippet);
    expect(
      within(row).getByText(`${ENTRY_HIT.character_name}${SEPARATOR}Harbour at dusk`),
    ).toBeInTheDocument();
    expect(row.textContent ?? "").not.toContain(ENTRY_START);
  });

  it("an entry of a never-renamed session shows <character> · <local date> with no time — S034_004_DoD7", async () => {
    serve(results({ entries: [ENTRY_HIT] }));
    renderScreen(`${SEARCH_PATH}?q=bold`);
    await flush();

    const row = rowBlock(await page().findByRole("region", { name: "Entries" }), ENTRY_HIT.snippet);
    expect(
      within(row).getByText(`${ENTRY_HIT.character_name}${SEPARATOR}${ENTRY_START}`),
    ).toBeInTheDocument();
    expect(row.textContent ?? "").not.toContain(localTime(ENTRY_STAMP));
    expect(row.textContent ?? "").not.toMatch(/\d{2}:\d{2}/);
  });
});
