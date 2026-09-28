# Quick reference

Dense, agent-first index of `docs/architecture/`. Exempt from the doc-length
rule. Every line here is a pointer or a fact — the reasoning lives in the doc
named beside it. **Where this file and another doc disagree, the other doc wins.**

## Doc map — where to look for what

**Twelve docs.**

| Doc | Read it when you need |
|---|---|
| `overview.md` | System context, actor→surface map, the admin surface list, dev/prod topology, **the full stack decision list with rationale** (including the five post-first-pass decisions), the deferred list |
| `quick-reference.md` | This file — the index |
| `data-model.md` | Tables and columns, **snowflake identifiers**, ownership/isolation columns, `users.role`, `auth_sessions`, the merged `messages` table + its two views, archive semantics, `vec0` + FTS5 tables, drift registry, the export/import contract sketch |
| `domain-rules.md` | **The role ladder + R1–R12, the cross-cutting invariants.** Read before touching any feature |
| `backend-structure.md` | FastAPI layout, routers/services split, `require_role`, **SQLAlchemy Core**, `pydantic-settings`, the `"$ENV_VAR"` secret pointer, `app/ids.py`, **the JSON id boundary**, the stream routes, settle/re-open, the `(( ))` seam, the typed error model, `/api/health`, `/api/me`, the connection probe's two routes, **schema evolution (registry + admin-applied Alembic batch DDL)** |
| `frontend-structure.md` | Vite multi-entry, the `admin` entry's boot + async gate, per-page MobX stores, routing inside the `app` entry, **"ids are strings"**, the API client, the SSE consumer |
| `workspace-shell.md` | The `app` entry's one screen: the three columns, **all geometry**, the note wall's two modes, **layout persistence**, the stream, the ruler and the current zone, the kind switch and settle, the wall's contents, the character page, the user menu, the model picker, and the reversal record for the deleted splitters |
| `ui-conventions.md` | Everything that is **not** the shell: icons + the shared `IconButton` + the full icon table, the accessibility floor, tables, **the list/modal/MobX-draft/confirm CRUD conventions**, no-toasts, never-optimistic, page state |
| `admin-surfaces.md` | The `admin` entry in full: 3 routes + 404, shell, the admin gate and why it deviates, the Users / LLM Servers / Database pages |
| `llm-and-streaming.md` | The one LLM client, resolve→validate→call, the SSE frame protocol, the tool loop, context assembly and its exclusions, translation |
| `search-and-retrieval.md` | Hybrid vec+FTS+RRF, `memo_search`, `session_search` (**vector arm only**), my-search (**applies no reach-flag predicate**), embedding lifecycle, rebuild |
| `deployment.md` | Ports, `start.ps1`, nginx directives (and the five deliberate deviations), compose, the `supervisord` ordering window and the admin boot, the single-generator guarantee, config conventions |

Requirements are **not** here. They are in `docs/product/` and are cited by id.
The id registry is `docs/product/quick-reference.md`.

**Splitting note.** A doc splits when it has come to cover **two subjects**, not
when it crosses a line count (`CLAUDE.md`). Two splits are **identified and not
authorized** — a new top-level doc must come from the architect's briefing:

- **`session-stream.md`** — would lift the stream routes, settle/re-open and the
  `(( ))` seam out of `backend-structure.md`, which is genuinely two subjects now.
  The backend counterpart to `workspace-shell.md`. **Not authorized, not done.**
- **`forms-and-lists.md`** — would lift the CRUD conventions out of
  `ui-conventions.md`. **Not authorized, not done.**

Recorded here so both are visible rather than rediscovered.

## Ports

| Role | Port |
|---|---|
| uvicorn / FastAPI (dev; loopback-only in prod) | **8184** |
| Vite dev server | **8193** |
| nginx published by compose | **8193** → container `:80` |

RPHelper = BookWriter minus 1, so both run in parallel. **Vite dev server and
dev-compose nginx share 8193 — run one or the other, never both.** No TLS
anywhere (`_TBD:` in `deployment.md`).

## Commands

Canonical source is the **root `CLAUDE.md`**. Repeated here for lookup only:

```
Backend  (run from backend/)
  test       .venv/Scripts/python -m pytest
  typecheck  .venv/Scripts/python -m mypy app
  lint       .venv/Scripts/python -m ruff check .
Frontend (run from frontend/)
  build      npm run build
  test       npm test
  typecheck  npm run typecheck
```

Dev: `start.ps1 -app` and `start.ps1 -ui` in **separate terminals**.

## Paths

```
backend/app/{routers,services,models,db}/     backend code (mypy target: app)
backend/app/ids.py                            the snowflake generator (not services/, not db/)
backend/tests/                                pytest target
backend/app/db/{schema,drift,sync}.py         registry / introspection / Alembic batch DDL
frontend/src/{bootstrap,login,admin,app}/     the four Vite entries
frontend/src/shared/                          api client, SSE consumer, IconButton
frontend/src/global.css                       hand-written stylesheet 1 of 2 — resets only
frontend/src/shell.css                        hand-written stylesheet 2 of 2 — workspace layout only, imported by the `app` entry alone
data/rphelper.sqlite                          the only state; /app/data in prod
docs/product/                                 requirements — read-only
docs/product/quick-reference.md               the id registry
docs/architecture/                            this doc set
docs/plans/CLAUDE.md                          the pipeline contract
```

localStorage key: **`rphelper.workspace-layout`** (renamed from BookWriter's — must
not be copied verbatim).

## Ids — the one rule that fails silently

**Every primary key is a snowflake** minted in application code before the INSERT
(`data-model.md`'s Identifiers section; 41-bit ms epoch `2026-01-01Z` / 10-bit node
id / 12-bit sequence). No `AUTOINCREMENT`, no `position` column — `ORDER BY id`
**is** the stream order.

**The boundary rule, stated in four docs because it fails silently and late:**

```
int64      in SQLite and in Python
decimal    STRING in every JSON payload — request body, response body,
           a DomainError's `detail`, and every SSE frame
string     in TypeScript, end to end
```

- **A TypeScript `id: number` anywhere is a defect** (`frontend-structure.md`,
  `data-model.md`). No `parseInt`, no numeric sort, no arithmetic.
- **A bare `int` id field on a pydantic model is the defect on the backend side.**
  `models/` converts, and only `models/` (`backend-structure.md`'s
  `SnowflakeOut` / `SnowflakeIn`).
- Reason: a snowflake passes `Number.MAX_SAFE_INTEGER` about **25 days** after the
  epoch, so an id reaching JS as a number rounds — possibly onto another row's id.
- **SSE frames carry the rule in full**: `accepted.message_id` and
  `done.message_id` are strings. `call_id` is **not** an id in this sense — it is
  the provider's opaque tool-call identifier.
- **Ids are not secrets**, and that grants nothing: every read path is scoped by
  `user_id` at the query level (R5).

**Flip condition:** the layout *and* the string boundary assume **exactly one
generator process per node id** (one container, one uvicorn — `deployment.md`). A
second worker or a syncing second instance re-opens both.

## Stack

FastAPI + `pydantic-settings` · **SQLAlchemy Core (not the ORM)** · SQLite (one
file: rows + `sqlite-vec` `vec0` + FTS5) · **Alembic — batch DDL only, not a
migration framework** (no `versions/`, no version table, no startup upgrade;
`db/schema.py` is the source of truth and the admin drift page applies —
`overview.md`, `backend-structure.md`) · React 19 + TS + Vite multi-entry ·
Mantine 7 (`core`/`hooks`/`tiptap`; **`form` present but unused, `notifications`
absent**; **`AppShell` in the `admin` entry only** — the `app` workspace is a
hand-written CSS grid)
· MobX 6 + `mobx-react-lite` · `react-router-dom` 7 · `@tabler/icons-react` `^3.40`
· TipTap + `tiptap-markdown` (edit) + `react-markdown` (render) · **`@dnd-kit`
(used — note reorder only)** · SSE over POST · HttpOnly `SameSite=Lax` cookie ·
nginx + uvicorn under `supervisord` in one container.

No Tailwind / CSS modules / styled-components. **Exactly two hand-written
stylesheets:** `global.css` (resets only, every entry) and `shell.css` (the `app`
workspace's layout only — grid, `--navw` rail, the 820px media query; the `app`
entry alone). Everything else is Mantine (`frontend-structure.md` owns the
division; `workspace-shell.md` carries the same decision).

## The four frontend entries

| Entry | Actor | Realizes |
|---|---|---|
| `bootstrap` | ACT-003, pre-database | FEAT-001 |
| `login` | unauthenticated | FEAT-002 |
| `admin` | ACT-001 | FEAT-003, FEAT-004, FEAT-005, FEAT-018 (admin half) |
| `app` | ACT-002 | FEAT-006..FEAT-013, FEAT-017, FEAT-018 (user half), FEAT-020 |

Why: admin code never ships in the roleplayer's bundle (FEAT-019), and the
pre-database bootstrap state need not coexist with the authenticated shell.
Cross-entry navigation is a document navigation; the cookie travels with it.

## Roles — the ladder

```
{ roleplayer: 0, admin: 1 }        roleplayer = ACT-002, admin = ACT-001
```

`users.role` is an enum column, not an `is_admin` boolean. Backend:
`require_role(min_role)` dependency **factory** on every admin route — "at least
this rung". Frontend gating is **UX only**. Replaces BookWriter's
`{author, admin}`. Full reasoning: `domain-rules.md`.

## Admin area at a glance — `admin-surfaces.md`

| Route (under `/admin`) | Page | Realizes |
|---|---|---|
| `/` | Users | FEAT-003 |
| `/llm-servers` | LLM Servers | FEAT-004 |
| `/database` | Database | FEAT-005 + FEAT-018 whole-database |
| `*` | Not found | — |

- `BrowserRouter basename="/admin"`, Mantine **`AppShell`** (`header` 56, `navbar`
  220 / `sm`), **no `padding`** (pages bring `Container size="lg" py="md"`), no
  `aside`, no breadcrumbs, **flat `<Routes>`** (no `<Outlet/>`). Back-to-app is a
  real `<a href="/">`, not a router `Link`.
  **`AppShell` lives here and only here** — the `app` entry's shell is a
  hand-written CSS grid (`workspace-shell.md`). The asymmetry is deliberate and is
  not an inconsistency to tidy up.
- **Gate:** `main.tsx` awaits `GET /api/me`, then mounts or redirects — nothing
  rendered meanwhile. Pure `resolveAdminAccess(currentUser)` + impure async
  `enforceAdminAccess()`. Deny cases: no session → `/login`; session but no
  resolvable user → `/login`; role not admin → `/`. **A 502/network failure is not
  a deny** (`deployment.md`).
  **Deviation:** BookWriter decodes a JWT pre-mount; impossible here — HttpOnly
  cookie **and** FEAT-003's disable-ends-sessions needs revocable server-side
  sessions.
- **Database page — `Create` and `Sync` are the schema-evolution mechanism.**
  Per-row, administrator-triggered, executed by `db/sync.py` via Alembic batch
  operations (SQLite cannot drop or retype a column in place). `Create` = UC-015's
  missing tables; `Sync` = an existing table whose shape moved. **Seed is not
  carried across** (`_TBD:`, no seed data exists). Nothing runs at boot.
- **Dropped from BookWriter, deliberately:** `AssistantModesPage`,
  `SubAgentsPage` — authoring-domain, no RPHelper analogue. Do not re-add.
- **Nav:** static declaration table → `NavLink`s, pure
  `isNavItemActive(pathname, item)` (segment match + `exact` for root), **not**
  react-router's `end`. Icons `IconUsers` / `IconServer2` / `IconDatabase`.
- **Shell state:** MobX `AdminShellState { navbarOpened }` via
  `useState(() => new …)`. **Not `useDisclosure`** — custom hooks must not hold
  reactive state.

### Admin/CRUD conventions — `ui-conventions.md`

Plain Mantine `Table` `striped highlightOnHover`, no data-table lib · row actions
in an overflow `Menu` behind `IconDots` in a trailing `w={60}` column, **never**
inline icon buttons · **no sorting / filtering / pagination anywhere** (small
cardinality; `_TBD:`) · centered `Loader` on an idle/loading status · inline red
`Text`/`Alert` above the table · **no empty-state component** (inherited weak
spot) · create/edit is **always a `Modal`**, with **two named workspace
exceptions** — in-place edit of a settled entry / zone message / note (UC-078,
US-104, US-109, US-110, US-115) and the character **draft page** (UC-074, US-097)
· **`@mantine/form` NOT used** — per-modal MobX `*Draft.ts` class (observable
fields, `serverErrors`, `submitStatus`, `clientErrors`/`errors`/`canSubmit`
getters) with an **external** `submitX(draft, …, onSaved, signal?)`, never a method
· fresh draft per open via conditional mount · modal open/target flags are
component-local `useState` (view state, not domain state) · **no toasts**
(`@mantine/notifications` absent) — success = modal closes + list refreshes ·
**never optimistic** — re-load after every mutation, `void` + non-rethrowing catch
(the workspace narrows the re-load to the edited row, same intent) · **confirm
step** on disable account / delete LLM connection / rebuild index (designed, not
inherited; no AC requires it) · page state = `makeAutoObservable` class **with no
methods** + free `loadX`/`xAction(state, …, signal?)` that `runInAction` and
early-return on abort, driven from `useEffect` + `AbortController`.

### Admin API facts

- `GET /api/me` → `{id, username, role}`, **`id` a decimal string**; **401** when
  no session **or** the account no longer resolves (disabled — FEAT-003). Own
  identity only. Three consumers: the admin gate, the app's user menu (UC-071,
  US-093), and sign-out.
- **Two** routes over **one** probe primitive: list-available-models (UC-012/013)
  and **test connection** (UC-011, own typed result). Test writes
  `llm_servers.last_test_*`; a failed test never blocks registration.
- API key is **never returned**. Edit semantics: empty/untouched = **leave
  unchanged**; explicit empty string = **clear**. Value must start with `$`
  (secret pointer) or it is rejected on write.
- Models modal renders `available ∪ already-enabled`; a **failed probe** shows an
  error and clears `available` but **must not disturb the selection**.

---

## Key invariants — the short list

Numbers are the `domain-rules.md` rule ids. **Read that doc for the reasoning; do
not act on these one-liners alone.**

| # | Invariant |
|---|---|
| **R1** | Config inherits `user → character → session` for model / system prompt / tools; RP language + preferred language inherit `user → session`, **skipping character**. `characters` has no language columns — schema-enforced, deliberate (FEAT-013, UC-048, UC-050) |
| **R2** | Memo chain is a **union** over user + character + setup? + session. With no setup it degrades to user+character+session **with no gap** — same query, one fewer OR-term. No sentinel setup row (FEAT-007, UC-046) |
| **R3** | A note's reach is **two independent booleans, `is_enabled` and `is_forced`** — not one three-valued column. Defaults `is_enabled = true`, `is_forced = false`. Disabling **preserves** `is_forced`, so re-enabling restores the mode (US-101). **`is_enabled` gates first; `is_forced` is consulted only afterwards** — selecting on `is_forced` alone prompts a disabled forced note, the exact leak the split made expressible. `NOT is_enabled` reaches the assistant by **NO path** — not context, not tools, not error payloads. **Constrains the assistant only: my-search applies neither flag.** Order is a third axis (`sort_key`, within a level). Memos never archive (FEAT-012, UC-042, UC-044, UC-045, UC-052, UC-075) |
| **R4** | **No silent model fallback.** Resolution yields a model *reference*, unvalidated; validation happens at **use time** against enabled models and raises typed `model_not_enabled` carrying which level set it. Never skip a disabled level and keep walking. US-106's "first enabled model" floor is **materialised onto `sessions.model_ref` on first compose**, so it cannot drift. Same for the embedding designation → `no_embedding_model` (FEAT-004, FEAT-013, UC-012, UC-050) |
| **R5** | **A `model → dependent sessions` query must not exist** on any admin surface — answering it discloses other users' sessions. "Are you sure? N sessions use this model" is a forbidden UI pattern, and **the LLM Servers page's confirm dialog is where it will be attempted**. Every read path scoped by owner **in the query** (FEAT-019, UC-012, UC-065, UC-066) |
| **R6** | Archive = out of the working list, never destroyed, always restorable. `archived_at` nullable, **no delete path** for characters/setups/sessions. No "finished" state. Memos are the contrast: they do not archive (UC-025, UC-067, UC-068) |
| **R7** | Settling **buries** the group under the settled head; re-open is allowed **only while the current zone below is empty**; a buried group **never reaches the assistant again**, then or later. Deliberate asymmetry: a settled turn is editable forever and the assistant reads the current version (UC-029, UC-036, UC-037, UC-038, UC-078) |
| **R8** | Translations are a success-only cache keyed `(message, target language)`, in their own table, and **never enter context**. Only settled rows are translatable — in practice only `kind='partner'` (FEAT-011, UC-039, UC-041) |
| **R9** | The assistant's reach is **exactly three tools**. A failed tool is a tool *result* — the exchange continues. The assistant never files anything into the record (ACT-004, UC-051, UC-053) |
| **R10** | The roleplayer's text is committed **before** any model call; a model failure loses nothing, and the `accepted` frame makes that observable. An enormous paste warns but is **never refused** (UC-032, US-035.AC-2) |
| **R11** | **The ruler: settle is the only door into the record**, with one exception — a pasted partner block, born settled (US-121). The **current zone is a set, not a row** (`related_to IS NULL AND settled_at IS NULL`), so US-125 needs no constraint. Re-open is settle's exact inverse, gated on an empty zone, and applies only to a head that **has** a buried group — otherwise `nothing_to_reopen`. **Raw `messages` is touched by exactly two operations, settle and re-open**; every other reader goes through the `settled_entries` / `current_zone` views (FEAT-009, FEAT-010, UC-035, UC-037, UC-083) |
| **R12** | `(( ))` is **parsed once, at settle, and stored text is never re-parsed.** Wholly parenthesised → `kind='decision'`; a fragment inside a draft is stripped from the head row in the same transaction and is not preserved. **Partner text gets no special treatment.** Three layers: server decides, system prompt instructs the model, client previews and is never authoritative (UC-081, UC-084, US-129, US-130, US-131) |

## SSE frame protocol

```
accepted | token | tool_start | tool_result | tool_fail | error | done
```

- **`accepted` is emitted once, before the first `token`**, and carries the
  **roleplayer's** committed zone row id — so an in-place edit of a just-sent
  message can `PATCH` without waiting for a reload (US-115). It makes R10's
  ordering observable and arrives on the failure path too.
- `done` mandatory on success and carries the **assistant's** row id; a stream
  ending without it = `llm_unreachable`. **Both ids are decimal strings.**
- `error` and `done` mutually exclusive and terminal.
- **`tool_fail` is NOT terminal** (R9).
- `error` carries the same `{code, message, detail}` shape as JSON errors.
- `tool_result` carries a **summary**, never raw retrieved content.
- Frames are built in one place, `services/llm/frames.py`.
- One streaming route: **`POST /api/sessions/{id}/zone/compose`**. Its
  non-streaming sibling `POST /api/sessions/{id}/zone/messages` makes no model
  call and returns JSON.
- POST + JSON body → client uses `fetch()` + `body.getReader()` + `TextDecoder({stream:true})`, split on `"\n\n"`, keep the trailing partial frame. **Not `EventSource`** (GET-only).
- App sets `X-Accel-Buffering: no`; nginx also sets `proxy_buffering off`.

## Context assembly — what is in, what is out

**In:** resolved system prompt + character sheet + **enabled AND forced** memos
(level order user → character → setup? → session, then by `sort_key`) +
RP-language instruction + the `(( ))` reading instruction + enabled tool
descriptions; and, as the message list, the **union of the `settled_entries` and
`current_zone` views** for this session, `ORDER BY id`. A `kind='decision'` row is
context like any other settled row (US-122).

**Out, each with the rule that forbids it:** memos where `NOT is_enabled` (R3 —
absolute, whatever `is_forced` says) · memos where `is_enabled AND NOT is_forced`
(R3 — `memo_search` only) · **buried rows, excluded by construction** at the view
boundary rather than by a predicate assembly writes (R7/R11/UC-038) · translations
(R8) · other users' material (R5) · other characters' sessions (UC-054).

Assembly names **no table** — a query here selecting from raw `messages` is a
defect. Messages and forced memos are read **live**; nothing is cached.

## Search at a glance

| Surface | Arms | Scope | Notes |
|---|---|---|---|
| `memo_search` (FEAT-014) | vec + FTS, RRF | `user_id`, `is_enabled AND NOT is_forced`, the 4-level chain | `is_enabled` gates first; works with no setup (one fewer OR-term, not a second code path) |
| `session_search` (FEAT-015) | **vec only — no BM25, no RRF step** | `user_id` **and** `character_id`, excl. current | semantic-only is a product decision (challenge C5); BM25 over `session_fts` (`title`, `partner_label`) would be a partner-name matcher — do not turn the FTS arm on. `session_fts` is kept for my-search. Reversible at low cost; flip condition in `overview.md`. `session_vec` composes from `settled_entries` and **must include decisions** (US-122.AC-2) |
| my-search (FEAT-017) | vec + FTS, RRF **within each kind** | `user_id`; 5 corpora (characters, setups, sessions, entries, memos) | ACT-002 UI, **not** a tool; grouped by kind, each hit jumps to its target. **Applies no `is_enabled`/`is_forced` predicate at all** (R3 binds the assistant, not the owner) — mark disabled hits visibly. Its entry corpus is the **`settled_entries`** view |

Filter first (relational), then rank. `sqlite-vec` KNN is **exact** — no recall
tuning. RRF with `k = 60`, ranks only, no score normalisation. All three go through
one narrow port so the store is swappable (flip condition in `overview.md`).

**Index tables:** `memo_fts(body)` — **`body` alone, because `memos` has no
`title` column** (US-119); `message_fts(text)` — **renamed from `entry_fts`** with
the table it indexes, external content on base `messages`, restricted to settled
rows by triggers; `session_fts(title, partner_label)`. Vector tables `memo_vec`
and `session_vec`.

**A memo hit's identity is a snippet plus its chain level.** There is no title to
fall back to and none may be re-introduced to tidy a list.

Embeddings are written in the **same transaction** as the relational write. A
**reach-flag change or a reorder re-embeds nothing** — that is the payoff of one
store. `session_vec` refreshes on settle, a settled-text edit, and re-open.

**The deliberate write asymmetry:** a memo create/body edit with no embedding
model **fails the whole transaction**; a message edit / settle / re-open
**succeeds, degraded** (US-112 — the record must not be blocked by an
instance-level omission). Do not harmonise the two.

## Typed errors

Wire shape: `{ "error": { "code", "message", "detail" } }`. Full table in
`backend-structure.md`.

`model_not_enabled` (carries the level that set it) · `no_embedding_model` ·
`secret_ref_missing` · `llm_unreachable` · `tool_failed` (a tool *result*, not a
stream error) · `translation_failed` · **`zone_empty`** (settle with nothing in
the zone) · **`zone_not_empty`** (re-open while the zone is not empty) ·
**`nothing_to_reopen`** (the head has no buried group — a pasted partner block) ·
**`message_not_editable`** (edit targets a buried row) · `already_configured` ·
`account_disabled`.

**`discussion_not_resumable` is gone.** It named a table that no longer exists and
a condition that has changed; `zone_not_empty` replaces it and the rename is not
cosmetic.

`detail` never carries another user's data, never a count derived from it, never a
body from a note where `is_enabled` is false — and **any id in it is a decimal
string**.

## UI geometry constants — `workspace-shell.md`

**Nothing in the workspace resizes.** The two hand-rolled splitters and the
fixed-height answer box are **deleted**, with a reversal record and a flip
condition in `workspace-shell.md`. `docs/product/` asks for no resizable column
anywhere; the only drag it requires is note reordering.

| Thing | Value |
|---|---|
| Tree column, expanded | `252px` |
| Tree column, collapsed (icon rail) | `48px` |
| Wall, floating (absolute overlay + shadow) | `min(320px, 84vw)` |
| Wall, pinned (a real grid column) | `320px` |
| Stream column | `max-width: 720px`, centred, `padding-inline: 18px` |
| Composer | same 720px / 18px; text area `min-height: 42px`, **no max**, no handle |
| Responsive threshold | `820px` (= 252 + 720 + 320; **not** a Mantine token) |

**These rules live in `frontend/src/shell.css`** — the grid, the `--navw` custom
property and its collapsed-rail class, and the `820px` media query. Not
`global.css` (resets only), not inline style objects (a class toggle and a media
query are not per-element style), not CSS Modules (forbidden).

- The shell is a **hand-written CSS grid, not `AppShell`** — the wall is an
  absolute overlay in one mode and a real column in the other, which
  `AppShell`'s navbar/main/aside model cannot express.
- **Collapse is a class that re-points one custom property** (`--navw`): one
  number, a browser-driven transition, zero React re-renders.
  `minmax(0, 1fr)` on the second track is load-bearing.
- **The composer grows with its content** — a deliberate reversal of the old
  "no auto-grow" rule, whose only reason was the deleted answer box.
- With **no session open the wall is not shown at all** (US-095).

**Layout persistence** — one localStorage record under
**`rphelper.workspace-layout`**:

```ts
type WorkspaceLayout = { navCollapsed: boolean; wallPinned: boolean };
```

**Two booleans and no numbers.** `asideWidth` and `answerBoxHeight` are gone.

- **Read is total and never throws** — per-field fallback, complete record, no
  `null`. There is nothing left to clamp.
- **A stored payload carrying the old numeric keys must be tolerated and
  ignored** — never rejected, never allowed to fail the parse. An existing
  install will have one, and a strict-schema parse would silently reset a
  roleplayer's layout.
- **Write is best-effort** `try`/`catch`, merged over a fresh total read, **on the
  toggle** — which is now the only time it can change.
- All of it in a **pure, DOM-free module**.

## Icons

`@tabler/icons-react` `^3.40`. `size={18} stroke={1.5}` main/header/composer,
`size={16}` inline, `size={14}` chevrons. Colour via the wrapping button's `color`.
**Every icon-only action goes through the shared `IconButton`** (`Tooltip` +
`ActionIcon` + `aria-label` from one `label` prop) — a deliberate deviation from
BookWriter, which has none.

**Three scopes, not two:** `IconButton` governs toolbar / header / composer /
inline actions; **table rows use the overflow `Menu`** instead, so a row holds
exactly one icon-only control (the `IconDots` trigger); **the stream's per-entry
actions sit inside the entry as `IconButton`s** — an entry is a document, not a
row (`workspace-shell.md`).

- **Settle and Send are labelled buttons, not icons.** Settle is the primary
  button, Send secondary. `IconMessageCheck` is **not** used anywhere — that
  earlier `_TBD:` is closed.
- **One chevron rotated**, not an `IconChevronDown`/`IconChevronRight` pair.
- `IconCopy` has no BookWriter precedent and is specified because the clipboard is
  the product's entire outbound boundary (UC-030, UC-082). Copy yields **plain
  text, never markdown** (US-124); a `kind='decision'` entry offers **no copy at
  all** (US-123).
- `IconArrowBackUp` for re-open — an undo for a mis-click, **absent** rather than
  disabled once the zone is non-empty (US-128).
- **Hover-revealed actions must also reveal on `:focus-within`**, and note
  reordering must have a keyboard path.

Full icon table, including the workspace additions and their open glyph
`_TBD:`s, in `ui-conventions.md`.

## `@dnd-kit` — used, for exactly one interaction

Reordering notes **within a level** on the wall (UC-076, US-102). The project's
first and only drag interaction; the earlier "available, unused" note is closed.

- **A note cannot cross a level boundary by dragging** (US-103.AC-2), enforced in
  the **drop handler**, not merely signalled in the drag preview —
  `memos.sort_key` is scoped within `(scope, scope_id)` and nowhere wider, so the
  move is not expressible in the schema and must not be expressible in the UI.
- Reordering **changes what the system prompt contains** (R3, US-102), which is
  why the **keyboard sensor is required, not optional**.
- Nothing else may use `@dnd-kit` without a requirement that asks for it.

## nginx — the five deliberate deviations from BookWriter

1. `proxy_http_version 1.1` + `Connection ''` on `/api/` — BookWriter hardened HMR but not SSE.
2. `X-Accel-Buffering: no` **from the app**, not only nginx's `proxy_buffering off`.
3. **`client_max_body_size 64m`** — the ~1MB default would turn US-035.AC-2 into a 413.
4. SSE directives on the **dev-compose** nginx too, not only prod.
5. Asset cache-control: hashed assets `immutable`, `index.html` `no-cache`.

Kept from BookWriter: `proxy_buffering off`, `proxy_cache off`,
`proxy_read_timeout 300s`. SPA fallback: one `location` per entry plus a catch-all.

## Deferred / non-goals

- FEAT-018's four export granularities in full detail — contract sketched in `data-model.md`.
- FEAT-016's `web_search` provider adapter — **seam only**.
- **Context compaction — an explicit non-goal** (`vision.md`), not an oversight.
  Context grows forever; nothing warns first.
- **TLS** — HTTP-only posture inherited.
- **Abandoning a current zone without settling** — a **product gap carried as a
  gap**, not a design decision: no route removes a message from the zone, so
  settle is the only way it empties (`overview.md`, `backend-structure.md`).

## Open `_TBD:` items across the doc set

| Where | What |
|---|---|
| `overview.md` | long RP eventually exceeds model capacity, unwarned (from `vision.md`); TLS if exposed beyond a LAN; **abandoning a current zone without settling** (carried from FEAT-010 C22 / UC-083); no concurrency target stated |
| `data-model.md` | **whether `vec0` handles sparse snowflake rowids as efficiently as dense ones — verify before FEAT-014/FEAT-015 are planned**; what happens to a materialised `sessions.model_ref` if the character is configured with a model afterwards; whether editing a non-partner settled message discards its cached translation (design deletes; inference beyond US-111); what text represents a session for `session_vec`; whether characters/setups get FTS tables; import collision / merge-vs-empty-target policy |
| `domain-rules.md` | R4 — the materialised `model_ref` question above, raised for `/product-spec`; R12 — **what happens when RP prose itself legitimately contains double parentheses** (carried from FEAT-010 C21 / US-130); a draft could silently lose text at settle |
| `backend-structure.md` | whether UC-080's first message should also draw an assistant reply (changes the response media type — FEAT-008's plan must settle it) |
| `frontend-structure.md` | where the archive toggle sits now that the character and session lists are gone (placement, not design) |
| `workspace-shell.md` | whether the character page's composer carries the kind switch or a setup choice (UC-080/US-117 decide neither); US-120's product `_TBD:` on what a settled **decision** does to the kind switch's alternating default, carried forward |
| `ui-conventions.md` | the wall pin and a note's "forced" flag are drawn with the **same pin glyph** for two unrelated meanings on one screen; the enabled/disabled note toggle's glyphs map onto no Tabler icon; `IconLanguage` toggle-state presentation unspecified; no wider accessibility target stated; **no sorting/filtering/pagination assumes small cardinality — revisit on a large account or list count** |
| `admin-surfaces.md` | **connection-test result taxonomy is a proposal** (`reachable`/`unreachable`/`auth_failed`/`model_list_empty`) — no AC specifies one; **Seed** exists in the inherited drift report and is **required by no UC** — RPHelper has no seed data at all, so it is recorded as prior art and not written up as a requirement (**Sync is no longer open** — it is Decision A's mechanism) |
| `llm-and-streaming.md` | no tool-iteration cap stated (a loop guard, not compaction); no `web_search` provider chosen; context grows forever with no warning |
| `search-and-retrieval.md` | RRF `k` / candidate depth / result count unmeasured; what text composes `session_vec` beyond its two fixed constraints; **how a disabled memo hit is marked in my-search results**; the **cost** of the per-write `session_vec` refresh on a long session; whether a per-session staleness marker earns a column; whether changing the embedding designation forces a rebuild |
| `deployment.md` | TLS / exposure model; `64m` body limit is a judgement; no logging/metrics/alerting posture |

**Closed in this delta — do not re-open or re-list:** the `session_vec` refresh
*policy* (→ refreshed in the same transaction as settle, settled-text edit and
re-open; US-110.AC-2 requires it — only its *cost* stays open); whether `@dnd-kit`
gets a reorder interaction (→ yes, US-102); the absence of a frame carrying the
roleplayer's committed row id (→ the `accepted` frame); `ui-conventions.md`'s
`id: number` page-state snippet (→ corrected to `string`);
`IconMessageCheck` for settle (→ a labelled button); the **ORM choice** (→
SQLAlchemy Core); **whether my-search shows disabled memos** (→ yes, no reach-flag
predicate at all); **whether `session_search` gets a lexical arm** (→ no, with a
flip condition); **schema evolution — migration files vs registry-only** (→ the
registry stays the source of truth, the administrator applies from the drift
page's `Create`/`Sync`, Alembic is the batch-DDL executor only, no migration
history and no startup upgrade; flip condition in `overview.md`); **where the
shell's layout CSS lives** (→ `src/shell.css`, a second hand-written stylesheet
beside `global.css`).

Not `_TBD:` but flagged for another owner: the my-search/disabled-note decision is
a **requirements gap resolved at the architecture layer** and **`/product-spec`
should ratify it into FEAT-017's ACs**. The **confirm step** on destructive admin
actions is required by **no acceptance criterion** and FEAT-003/004/005's planners
may revisit it.
