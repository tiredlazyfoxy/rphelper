# Feature 029 — My-search · feature-wide context

## What this feature is

The roleplayer's own search box. One query reaches everything they own — characters,
setups, sessions, entries and notes (memos) — and the results come back **grouped by kind**,
in a fixed order, each row a link that lands on the thing it names. It applies **only the
owner predicate**: no note flag filters a result (a disabled note is returned and shown as
disabled), and archived characters, setups and sessions are returned and shown as archived.
The box sits at the top of the tree; the collapsed rail keeps a trigger that opens the
results page with its own box focused.

The agreed boundary is `brief.md` in this folder (Definition, Scope In/Out). **Out:** the
assistant's tools (`026`, `027`), which apply the opposite flag rule on purpose — the
asymmetry is deliberate, not a bug to reconcile; maintaining any index (`024`); the port
itself (`025`).

## Product ids

Delivers **FEAT-017** (UC-058, UC-059, UC-060; US-074, US-075, US-076, US-118, US-137).
Also binds to UC-065 (privacy) and `domain-rules.md` R3, R5, R11.

| Criterion | Where it lands |
|---|---|
| US-074.AC-1 (every kind reachable from one query) | `002` (service), `003` (route), `005` (screen) |
| US-075.AC-1 (grouped, in order character, setup, session, entry, memo) | `002`, `003` (wire order), `005` (render order) |
| US-076.AC-1 (never another user's material), UC-065, R5 | `001` (characters, setups), `002` (sessions, entries, memos), `003` |
| US-137.AC-1 (disabled / not-forced memos returned; state never filters) | `002`, `003` |
| US-137.AC-2 (a disabled memo is shown as disabled) | `002` (`is_enabled` on the hit), `005` (marking) |
| US-118.AC-1 (box reachable, tree expanded) | `006` |
| US-118.AC-2 (trigger reachable from the collapsed rail) | `005` (rail → `/search`, box focused) |
| UC-060 (a result lands on what it names) | `004` (targets), `005` (links), `006` (entry anchor, wall open) |
| R11 (entries come from the settled record only) | `002` (through 025's entry scope; tested as an absence) |

## Build prerequisites — 024 and 025 must be delivered first

Features 001..016 are built. **017..028 are planned only.** 029 must not start until
**024** (`docs/plans/024.embedding-lifecycle/`) and **025**
(`docs/plans/025.hybrid-search-port/`) are delivered — 025 depends on 024.

**Binding rule for the 029 skeleton agent:** for every name below taken from a pending
plan, bind to the exact identifier frozen in that plan's `status.md` `## Skeleton` record.
Only when that record does not exist, fall back to the name used here. A frozen name that
differs is not a 029 spec problem; follow the frozen one.

- **025 — the port** (`app/services/search/`):
  - `ports.py`: `MemoSearchScope`, `SessionSearchScope`, `EntrySearchScope` — each requires
    `user_id`, accepts an optional extra-predicate builder (029 passes **none**). `SearchHit`
    with kind, id, score, snippet, memo `scope` / `scope_id`, entry `session_id`. A session
    hit's snippet is none; an entry hit's and a memo hit's snippet is plain text. **No
    `is_enabled` on the hit** (029 hydrates it).
  - `hybrid.py`: `search(connection, scope, query, limit, *, client_factory,
    timeout_seconds)` → hits best first. Blank query or `limit <= 0` → `[]`, no model
    opened. Memo and session scopes open the designated model and let
    `NoEmbeddingModelError`, `LlmUnreachableError` and the `secret_ref_missing` error
    propagate unchanged; the entry scope never opens the model. Absent or empty tables →
    no hits, not an error. It reads only and leaves no transaction open. **Sync**: it
    embeds through 024's `asyncio.run` bridge, so it must run on a thread with no running
    loop (a sync `def` route does).
- **024**: `app/db/search_tables.py` (`ensure_fts_tables`, `ensure_vector_tables` — test
  setup only), `app/services/embedding.py` (`DEFAULT_EMBED_TIMEOUT_SECONDS`, `write_vector`
  — test setup only), `get_llm_client_factory` in `app/dependencies.py`,
  `backend/tests/llm_fakes.py` (deterministic fake embedder + fake factory; scriptable to
  raise `LlmUnreachableError`; counts calls). `message_fts` holds settled record rows only.
- **017 step 007** builds the `/settings` screen where user-level notes live. A user-memo
  hit links to `/settings` whether or not that screen exists at build time; what renders
  there is 017's.

**Files 029 shares with other pending plans** (textual overlap, not dependencies — the coder
binds to whatever is in source at build time): `SessionScreen.tsx` (017 `011`, 018 `009`),
`SessionStream.tsx` (017 `011`), `StreamRecord.tsx` (022 `007` adds a discussion group under
each entry; the `<li>`, its ref and its key are unchanged), `main.py` (017 and 023 also
append routers). None of 017 / 018 / 022 touches `WorkspaceShell.tsx`, `CharacterTree.tsx`
or `/search`.

## Architecture this binds to

- `search-and-retrieval.md`: "The narrow port", "A memo hit is a snippet plus a level",
  "Query shape" (filters first), "My-search — FEAT-017" incl. "The entry corpus is the
  `settled_entries` view" and "Settled and ratified: my-search does show disabled notes"
  (its presentation `_TBD:` is closed by D7).
- `data-model.md`: "FTS5 tables" (its characters/setups `_TBD:` is closed by U2), `memos`
  (no title, no archive), the `settled_entries` view.
- `frontend-structure.md`: "Routing inside the `app` entry" (`/search`), "Ids are strings",
  "State — MobX 6, per-page stores, no context", "The API client".
- `workspace-shell.md`: my-search at the top of the tree, duplicated on the collapsed rail.
- `backend-structure.md`: Layout (`routers/search.py`, `services/search/my_search.py`); the
  error model; services import no `fastapi`.
- `domain-rules.md`: R3 (constrains the assistant, not the owner), R5, R11.

Cited, never copied.

## Files this feature touches

```
backend/
  app/services/search/my_search.py  # NEW — constants, LIKE corpora                         (001)
                                    #       + hydration reads, run_my_search orchestrator   (002)
  app/models/search.py              # NEW — response models                                  (003)
  app/routers/search.py             # NEW — GET /api/search                                  (003)
  app/main.py                       # registers the search router, docstrings                (003)
frontend/
  src/app/searchApi.ts              # NEW — wire types + fetch                               (004)
  src/app/searchState.ts            # NEW — page state, load, URL/target helpers             (004)
  src/app/SearchScreen.tsx          # NEW — box + grouped results                            (005)
  src/app/App.tsx                   # /search renders SearchScreen                           (005)
  src/app/CharacterTree.tsx         # header Search button → text input                      (006)
  src/app/SessionScreen.tsx         # reads ?entry= and ?notes=open                          (006)
  src/app/SessionStream.tsx         # passes the focus entry through                         (006)
  src/app/StreamRecord.tsx          # entry anchor: data attribute, scroll, highlight        (006)
```

**Not touched — a step that touches one is out of scope:** `db/schema.py` (no new table,
column or FTS table — U2), `db/search_tables.py`, `services/embedding.py`, every 025 module
under `services/search/`, `services/memos.py`, `services/sessions.py`, `errors.py`,
`dependencies.py`, `tests/conftest.py`, `tests/llm_fakes.py`, `WorkspaceShell.tsx` (the rail
button already navigates to `/search`; D9), `shell.css`, `global.css`, `shared/*`. No new
Python or npm dependency.

## User-confirmed decisions (binding)

### U1 — An embedding failure fails the whole search

When the memo or session port call raises (`no_embedding_model` 409, including `detail
{"reason": "dimension_mismatch"}`; `secret_ref_missing`; `llm_unreachable` 502), the request
fails with that error envelope **unchanged**. No partial groups, no lexical-only degrade.
The results page shows the failure inline (not a toast) and no groups. Consequence, stated
plainly: with no usable embedding model, my-search answers nothing — even a character-name
match. `outcome.md` records it.

### U2 — Matching per kind

| Kind | Mechanism | Matched on |
|---|---|---|
| character | case-insensitive substring `LIKE`, escaped (D3) | `characters.name`, `characters.sheet` |
| setup | case-insensitive substring `LIKE`, escaped (D3) | `setups.name`, `setups.description` |
| session | 025 session scope (vector arm only) | `session_vec` (024's composed text) |
| entry | 025 entry scope (lexical only) | `message_fts` over `settled_entries` |
| memo | 025 memo scope (vector + lexical, RRF), **no extra predicate** | `memo_vec`, `memo_fts` |

No new FTS table and no schema change: characters and setups are small and have no index.
The two LIKE corpora therefore sit **outside** the port — a recorded deviation from "all
three surfaces go through one port" (`outcome.md`). Memos get **no** `is_enabled` /
`is_forced` predicate at all (US-137.AC-1).

### U3 — Archived rows are included and marked

Archived characters, setups and sessions are returned (owner predicate only). Each such hit
carries `archived: true`; the UI marks it with the existing idiom (D7).

### U4 — Navigation, presentation, trigger

- Targets (exact paths in `004.context.md`): character → its page; setup → its character's
  page (setups have no route); session → the session; entry → the session with
  `?entry=<message id>`, scrolled to and briefly highlighted; memo → its level's page (user →
  `/settings`; character / setup → the character page; session → the session with the note
  wall opened). No per-note focus.
- A disabled memo row uses the wall idiom plus a "Disabled" badge (D7). Memo rows show
  snippet + level, never a title (US-119).
- The query lives in the URL: `/search?q=<text>`. The tree header's Search button becomes a
  text input (Enter submits). The collapsed rail keeps its Search button, which navigates to
  `/search`; the results page's box is focused on arrival. Blank `q` shows no results and
  makes no request.

## Planner / orchestrator decisions

### D1 — One route, five fixed groups

`GET /api/search?q=<text>` in `routers/search.py`, every route behind `require_user`. `q` is
optional (absent = blank). Answers **200** with one object holding five keys in UC-059 order
— `characters`, `setups`, `sessions`, `entries`, `memos` — each a list, possibly empty
(wire contract below). Blank `q` (empty or whitespace-only) → 200, all five empty, no
embedding call, no search SQL.

### D2 — Per-kind cap and order

- Each group holds at most **20** hits (one module constant in `my_search.py`, name frozen by
  the skeleton). It is passed to the port as `limit` and to the LIKE queries as their limit.
- Sessions, entries and memos keep the **port's order** (fused score, ties by id).
- Characters and setups (no score) are ordered by **`name` ascending, then `id` ascending**.
  Planner decision: `characters` has no `updated_at` in the harvested schema, name order is
  scannable and deterministic, and one rule serves both kinds.

### D3 — LIKE semantics

- The needle is the query **with leading/trailing whitespace stripped**, matched as **one
  substring** (not split into words).
- `%`, `_` and the escape character in the needle are escaped, and the statement declares
  the escape character, so user input can never act as a wildcard.
- Case-insensitivity is SQLite `LIKE`'s: **ASCII letters only**. A non-ASCII name matches
  only in the case typed. Recorded as a known limitation in `outcome.md`, not fixed here.
- A row matches when **either** of its two columns contains the needle; it appears once.

### D4 — Hydration (029's own owner-scoped reads)

The port returns ids, scores, snippets and memo levels only. 029 reads the display fields
with one owner-scoped read per kind (every statement carries `user_id = :user_id` on each
base table it names — R5):

| Kind | Hydrated from | Fields |
|---|---|---|
| session | `sessions` ⨝ `characters`, LEFT OUTER ⨝ `setups` | character name, setup name (null when no setup), `created_at`, archived |
| entry | `settled_entries` ⨝ `sessions` ⨝ `characters` | character name, the session's `created_at` |
| memo | `memos`, LEFT OUTER ⨝ `setups` for setup-level memos | `is_enabled`; the character id a character- or setup-level memo routes to |

A port hit whose id is missing from its hydration read is **dropped**, not raised. Entry
reads go through `settled_entries`, never raw `messages` (R11).

### D5 — Execution order and fail-whole

The orchestrator runs the two model-opening port calls (session, memo) **first**, then the
entry port call, then the two LIKE queries, then hydration, and only then builds the result.
An exception from any step propagates unchanged to the single `DomainError` handler; no
half-built result is ever returned. Order does not affect correctness (U1); it makes a
missing model cost no other work. **Known cost:** the query is embedded **twice** per search
(once per model-opening scope), because 025's port takes text, not a vector. `outcome.md`
flags it.

### D6 — Read posture

Every 029 read follows the existing list services' posture: the autobegun read transaction
is rolled back after the reads, on return **and** on raise (`services/memos.py` `_reading`,
~L238-246). It is replicated locally in `my_search.py` (private there, never imported).

### D7 — Presentation (closes `search-and-retrieval.md`'s disabled-hit `_TBD:`)

- **Archived** (character, setup, session rows): a gray light `Badge` reading "Archived" and
  the row's text dimmed — the tree's idiom.
- **Disabled memo**: the snippet in the wall's disabled idiom (`c="dimmed"` plus
  `td="line-through"`) **and** a gray `Badge` reading "Disabled". A forced or enabled memo
  gets no badge.
- Snippets render as **plain text**, not markdown: they are cut fragments of markdown, and a
  fragment rendered as markdown can open a structure it never closes. A deviation from
  `frontend-structure.md`'s "react-markdown renders search result snippets"; `outcome.md`
  records it.
- Mantine props only. No stylesheet, no class name.

### D8 — The landing URL contract

| Param | On | Meaning |
|---|---|---|
| `q` | `/search` | the query text, URL-encoded |
| `entry` | `/sessions/:id` | the message id to scroll to and highlight once the record loads |
| `notes` | `/sessions/:id` | value `open` opens the note wall on arrival |

An `entry` id not present in the loaded record does nothing (no error, no scroll). The
params are not removed from the URL after use.

### D9 — Focus on arrival, not a rail signal

The results page focuses its own box **on every navigation that lands on `/search`** (keyed
on the location's identity), whichever trigger caused it. The rail's existing button already
navigates to `/search`, so `WorkspaceShell.tsx` is not changed. Arriving from the tree input
moves focus to the page box too, which holds the same text.

## Wire contract — `GET /api/search?q=<text>`

Ids are decimal **strings** (`SnowflakeOut`). Timestamps serialize as every other response's
timestamps do.

```
{
  "characters": [ { "id", "name", "archived" } ],
  "setups":     [ { "id", "name", "character_id", "character_name", "archived" } ],
  "sessions":   [ { "id", "character_name", "setup_name" | null, "created_at", "archived" } ],
  "entries":    [ { "id", "session_id", "snippet", "character_name", "session_created_at" } ],
  "memos":      [ { "id", "scope", "scope_id" | null, "character_id" | null,
                    "snippet", "is_enabled" } ]
}
```

- `archived` is a boolean (`archived_at` is not null).
- memo `scope` is `"user" | "character" | "setup" | "session"`. `scope_id` is **null for
  `"user"`** (the stored value is the user's own id, which the client has no use for) and the
  level's id otherwise. `character_id` is the character page the memo routes to: `scope_id`
  for `"character"`, the setup's `character_id` for `"setup"`, null for `"user"` and
  `"session"`.
- Errors use the standard envelope `{"error": {"code", "message", "detail"}}`: 401 without a
  session; `no_embedding_model` 409; `llm_unreachable` 502; `secret_ref_missing` as
  `errors.py` declares it.

## Literals — the contract tests bind to

| Name | Exact value | Used by |
|---|---|---|
| per-kind cap | `20` | D2 (`001`, `002`) |
| route | `GET /api/search`, param `q` | D1 (`003`, `004`) |
| results page path | `/search`; with a query `/search?q=<encodeURIComponent(text)>` | U4 (`004`–`006`) |
| tree input accessible name | `Search` | `006` |
| page box accessible name | `Search query` | `005` |
| group headings, in order | `Characters`, `Setups`, `Sessions`, `Entries`, `Notes` | `005` |
| memo level labels | `User note`, `Character note`, `Setup note`, `Session note` | `005` |
| archived badge | `Archived` | `005` |
| disabled badge | `Disabled` | `005` |
| loading text | `Searching…` (U+2026) | `005` |
| no results (non-blank q, all empty) | `Nothing found.` | `005` |
| failure heading | `Search failed` (followed by the envelope's message) | `005` |
| retry button | `Retry` | `005` |
| entry anchor param | `entry=<message id>` | D8 (`004`, `006`) |
| wall-open param | `notes=open` | D8 (`004`, `006`) |
| entry highlight duration | `2000` ms | `006` |
| entry anchor attributes | `data-entry-id="<message id>"` always; `data-highlighted="true"` while highlighted | `006` |

## Cross-cutting constraints every step holds

- **Owner scope in SQL (R5).** Every statement 029 issues carries `user_id = :user_id` on
  every base table it reads. Isolation is tested as an **absence**: another user's row that
  would match on every arm never appears.
- **No flag predicate on memos (R3 constrains the assistant, not the owner).** Nothing in
  029 reads `is_forced`, and `is_enabled` is read only to report it.
- Backend: sync SQLAlchemy Core; functions take `connection` first, `user_id` second;
  `client_factory` / `timeout_seconds` keyword-only with the port's defaults (024 D9).
  `my_search.py` imports no `fastapi`. `mypy app` and `ruff check .` green after every step.
- Frontend: TypeScript only; `npm run typecheck` green. Pure data contracts (memory note):
  the MobX class holds observable fields only (`makeAutoObservable(this, {}, {autoBind:
  true})`); derivations and effects are free functions, effects `runInAction` after `await`
  and write nothing once aborted. Components reading observables are `observer`. Stores via
  `useState(() => new X())`, passed as props, no context. **Ids are strings** — no `number`
  id binding, no `parseInt`.
- Failures on the results page are inline with Retry; **no** `notifyFailure` call.

## Test conventions

**Backend** (from `backend/`): pytest, flat `tests/`, names
`test_<behavior>__S029_<SSS>_DoD<n>`.

- Each test file has its own engine fixture over the existing `db_settings` / `db_engine`
  (`schema.metadata.create_all`), file-local raw-insert helpers, ids **above 2^60**, two
  users A and B. `conftest.py` is untouched.
- Search tables via 024's `ensure_fts_tables` / `ensure_vector_tables` (small dim, e.g. 8);
  vectors via `write_vector` with the fake's pure `(text, dim)` vector. A designated model is
  raw `llm_servers` + `models` rows (`is_enabled`, `is_embedding_designated`,
  `embedding_dim`). The fake factory is passed as `client_factory=` (service) or via
  `app.dependency_overrides` on `get_llm_client_factory` (router). **The port is never
  mocked. No monkeypatching.**
- Failure cases create the vector tables first, so the expected raise does not depend on
  025's internal ordering of "open model" versus "table absent".
- Expected values come from this plan and from seeded data — never from calling the code
  under test.

**Frontend** (from `frontend/`): Vitest + RTL + user-event; `tests/app/<Name>.test.tsx` or
`tests/app/<module>.test.ts`; each `it` title ends `— DoD-N`; file header comment "Feature
029, step SSS (DoD-x..y)". Rendered components sit in `<AppProviders>` + `MemoryRouter`; a
`useLocation` probe observes navigation. `fetch` is stubbed per file with `vi.stubGlobal`,
routed by exact pathname. Ids are strings. Guards that must stay green:
`tests/conventions.test.ts`, `tests/stylesheets.test.ts` (no new stylesheet; `shell.css`
unchanged), `tests/ids-are-strings.test.ts`.

**Regression rule:** each step lists the existing test files it knowingly amends. If the
red-gate run shows a failure in an existing test file not listed in that step, it is a
`SPEC` hand-back; nobody edits an unlisted file.

## Vocabulary

| Term | Means here |
|---|---|
| **group** | one of the five per-kind result lists, in UC-059 order |
| **LIKE corpus** | characters or setups, matched by escaped substring outside the port (U2) |
| **port call** | one 025 `search` call for the session, entry or memo scope |
| **hydration** | 029's owner-scoped read of a kind's display fields (D4) |
| **target** | the in-entry path a hit's row links to (U4; paths in `004.context.md`) |
| **landing params** | `entry` and `notes` on `/sessions/:id` (D8) |
