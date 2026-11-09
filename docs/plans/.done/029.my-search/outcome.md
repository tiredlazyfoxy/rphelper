# Feature 029 — My-search · intended documentation changes

Planner section: the doc changes the architect applies once 029 ships. Grouped by target
file. "Un" / "Dn" refer to decisions in this folder's `context.md`.

## `docs/architecture/search-and-retrieval.md`

| Section | Intended change | Reason |
|---|---|---|
| My-search — "Five corpora, so five `SearchScope` variants through the same port" | Replace with the as-built mechanism: **three port variants** (session — vector only; entry — lexical over `message_fts` / `settled_entries`; memo — hybrid, **no extra predicate**) plus **two LIKE corpora outside the port** (characters: `name`, `sheet`; setups: `name`, `description`; escaped, case-insensitive substring, one needle, not tokenised). The product count of five corpora is unchanged | U2 |
| The narrow port — "All three surfaces go through one port" | Record the deviation: my-search's character and setup corpora do **not** go through the port, because there is no index for them and a port variant over plain `LIKE` would carry no arm. Flip condition: if characters / setups ever get an FTS or vector index, they become port variants and the LIKE path goes | U2 |
| My-search — "Settled and ratified: my-search does show disabled notes" | **Close the presentation `_TBD:`**: a disabled hit's snippet uses the note wall's disabled idiom (dimmed, struck through) plus a gray "Disabled" badge; enabled and forced hits carry no marker; the row shows snippet + level label, never a title | D7 |
| My-search | Record **fail-whole**: when the memo or session vector arm raises (`no_embedding_model` incl. `dimension_mismatch`, `secret_ref_missing`, `llm_unreachable`), the whole request fails with that envelope; no partial groups, no lexical-only degrade. Consequence: with no usable embedding model my-search returns nothing, not even a character-name match. The page shows the failure inline | U1 |
| My-search | Record **archived included**: archived characters, setups and sessions are returned (owner predicate only) and marked "Archived". This differs from `session_search`, which excludes archived sessions (027) — another deliberate asymmetry between the owner's search and the assistant's | U3 |
| My-search | Record the as-built result shape: five groups in UC-059 order, at most **20** per group (conventional, not measured — same `_TBD:` posture as RRF's constants); port order for sessions / entries / memos; `name`, then `id`, for characters / setups. Hydration is my-search's own owner-scoped read (session: character name, setup name, start time, archived; entry: session id, character name, session start; memo: `is_enabled`, routing character id) | D2, D4 |
| My-search | Record the **known cost**: each search embeds the query **twice** (memo and session scopes each open the model), because the port takes text. A port entry taking a pre-computed query vector would halve it; not done here | D5 |
| My-search | Record the **ASCII-only case folding** of `LIKE` as a known limitation for non-ASCII names / personas (the product's users often write in a non-native language). `_TBD: whether non-ASCII case-insensitive matching on characters and setups is required — docs/product/ does not say; raised, not decided._` | D3 |
| My-search — "Every result jumps to the session or entry it points to" | Record the landing targets: character → `/characters/:id`; setup → its character page; session → `/sessions/:id`; entry → `/sessions/:sessionId?entry=<messageId>` (scroll + 2 s highlight); memo → its level's page (user → `/settings`; character / setup → the character page; session → `/sessions/:id?notes=open`). No per-note focus | U4, D8 |

## `docs/architecture/data-model.md`

| Section | Intended change | Reason |
|---|---|---|
| FTS5 tables — characters / setups paragraph | **Close the `_TBD:`**: characters and setups get **no** FTS tables; my-search matches them with escaped `LIKE` over `characters.name` / `sheet` and `setups.name` / `description`. No schema change | U2 |
| FTS5 tables — `session_fts` | Note that FEAT-017 shipped **without** `session_fts` (024 U7 deferred it; sessions have no `title` / `partner_label` column to index). My-search's session corpus is the vector arm over `session_vec`. The paragraph saying `session_fts` "exists for FEAT-017's my-search" is stale | U2, 025 `outcome.md` flags |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| Layout — `routers/search.py`, `services/search/my_search.py` | As built: `routers/search.py` exposes `GET /api/search?q=` (sync `def`, `require_user`, shared client factory + configured timeout); `models/search.py` holds the response models; `my_search.py` holds the LIKE corpora, hydration and `run_my_search` | D1, `003` |
| Route surface | Add `GET /api/search?q=<text>` → 200 `{characters, setups, sessions, entries, memos}` (ids as strings; blank `q` → five empty lists, no embedding call); errors 401, 409 `no_embedding_model`, 502 `llm_unreachable`, `secret_ref_missing` | wire contract |
| Router registration order | The search router is included after the routers that preceded it at build time; the `main.py` docstrings name it | `003` |

## `docs/architecture/frontend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| Routing inside the `app` entry — `/search` | Record the URL contract: `/search?q=<text>` (the query lives in the URL so it survives the tree's remount on expand); blank `q` → no request. Add the two landing params on `/sessions/:id`: `entry=<messageId>` and `notes=open` | U4, D8 |
| Routing — my-search trigger | As built: the tree header's trigger is a **text input** (Enter submits); the collapsed rail keeps its Search button, which navigates to `/search`; the results page focuses its own box on every arrival | U4, D9 |
| Markdown — "Rendering … search result snippets" | **Correct**: search snippets render as **plain text**, not via `react-markdown` — they are cut fragments of markdown and may open a structure they never close | D7 |
| Where a store's file lives | Add `src/app/searchState.ts` / `searchApi.ts` / `SearchScreen.tsx` as the my-search page modules | `004`, `005` |

## `docs/architecture/workspace-shell.md`

| Section | Intended change | Reason |
|---|---|---|
| The three columns — my-search at the top of the tree | As built: a text input in the tree header (replacing the icon button); the rail keeps the icon button | U4 |
| The stream — the settled record | Add the entry anchor: each settled entry carries its message id as a data attribute; arriving with `?entry=` scrolls that entry into view once and highlights it for 2000 ms | D8 |
| The wall has two modes | Add: `?notes=open` opens the wall on arrival; this does not change the rule that "open" does not survive a reload | D8 |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Paths / routes | Add `routers/search.py`, `models/search.py`, `services/search/my_search.py`, `GET /api/search`, and the three frontend modules | files list |

## Flags for other owners

- **`025` / a future port revision.** My-search embeds the same query twice per request
  (D5). A port entry that accepts a pre-computed query vector, or a multi-scope call, would
  remove the duplicate provider call.
- **`/product-spec`.** ASCII-only case folding for character / setup matching (D3) — whether
  non-ASCII case-insensitive matching is required is not stated in `docs/product/`.
- **`017` step `007`.** User-level memo hits link to `/settings`; that screen is where the
  roleplayer finds the note. No per-note focus is provided there.

## Observations

- Step 004: the non-`ApiError` fallback message had to be duplicated — the house generic text
  (`"Something went wrong. Please try again."`) lives as a module-private constant inside
  `shared/notifyFailure.ts`, and the results page must not notify, so `searchState.ts` repeats the
  literal. Possible impact: note in `frontend-structure.md` ("The API client" / failure handling)
  that an inline-failure page needs that text exported, or export it from `shared/apiError.ts`.

- Step 006: the landing params are read in exactly one place. `SessionScreen` is the only module in
  the session chain that may call a router hook — `SessionStream` and `StreamRecord` take the focus
  entry id as a plain prop, because they are mounted router-free in seven delivered suites and a
  `useSearchParams` / `useLocation` call inside either would throw there. 029 is also the first
  caller of `useSearchParams` and the first `scrollIntoView` in `src/`. Possible impact: state the
  "only the screen reads the URL, children get props" rule in `frontend-structure.md` under
  "Routing inside the `app` entry", so a later feature does not reach for a router hook deeper in
  the chain.

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B2 (the LLM/search/operations layer — `llm-and-streaming.md`, `search-and-retrieval.md`, `deployment.md`, `admin-surfaces.md`, `overview.md`) and B3 (the frontend layer — `workspace-shell.md`, `frontend-structure.md`, `ui-conventions.md`, `forms-and-lists.md`).
Rejected items: none
Notes: Its `_TBD:` asking whether non-ASCII case-insensitive matching is required is answered, not carried — `US-147` requires any script, so the ASCII-only `LIKE` folding is recorded as defect D-05. Both `## Observations` applied in B3, and the "five corpora, five variants" sentence becomes three port variants plus two LIKE corpora, with the product's count of five corpora unchanged.
