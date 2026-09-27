# Quick reference

Dense, agent-first index of `docs/architecture/`. Exempt from the ~400-line doc
budget. Every line here is a pointer or a fact — the reasoning lives in the doc
named beside it. **Where this file and another doc disagree, the other doc wins.**

## Doc map — where to look for what

**Eleven docs.**

| Doc | Read it when you need |
|---|---|
| `overview.md` | System context, actor→surface map, the admin surface list, dev/prod topology, **the full stack decision list with rationale** (including the five post-first-pass decisions), the deferred list |
| `quick-reference.md` | This file — the index |
| `data-model.md` | Tables and columns, ownership/isolation columns, `users.role`, `auth_sessions`, archive semantics, `vec0` + FTS5 tables, drift registry, the export/import contract sketch |
| `domain-rules.md` | **The role ladder + R1–R10, the cross-cutting invariants.** Read before touching any feature |
| `backend-structure.md` | FastAPI layout, routers/services split, `require_role`, **SQLAlchemy Core**, `pydantic-settings`, the `"$ENV_VAR"` secret pointer, the typed error model, `/api/health`, `/api/me`, the connection probe's two routes |
| `frontend-structure.md` | Vite multi-entry, the `admin` entry's boot + async gate, per-page MobX stores, routing, the API client, the SSE consumer |
| `ui-conventions.md` | `AppShell` shell, the two resize behaviours + constants, layout persistence, icons + `IconButton`, **the list/modal/MobX-draft/confirm CRUD conventions** |
| `admin-surfaces.md` | The `admin` entry in full: 3 routes + 404, shell, the admin gate and why it deviates, the Users / LLM Servers / Database pages |
| `llm-and-streaming.md` | The one LLM client, resolve→validate→call, the SSE frame protocol, the tool loop, context assembly and its exclusions |
| `search-and-retrieval.md` | Hybrid vec+FTS+RRF, `memo_search`, `session_search` (**vector arm only**), my-search (**shows `disabled` memos**), embedding lifecycle, rebuild |
| `deployment.md` | Ports, `start.ps1`, nginx directives (and the five deliberate deviations), compose, the `supervisord` ordering window and the admin boot, config conventions |

Requirements are **not** here. They are in `docs/product/` and are cited by id.

**Line-budget note.** `ui-conventions.md` and `backend-structure.md` now exceed
the ~400-line budget. The named split candidate is a `forms-and-lists.md` carved
out of `ui-conventions.md`'s CRUD section — **not authorized, not done**: a new
top-level doc must come from the architect's briefing (`CLAUDE.md`). Recorded here
so the overrun is visible rather than discovered.

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
backend/tests/                                pytest target
frontend/src/{bootstrap,login,admin,app}/     the four Vite entries
frontend/src/shared/                          api client, SSE consumer, IconButton
data/rphelper.sqlite                          the only state; /app/data in prod
docs/product/                                 requirements — read-only
docs/architecture/                            this doc set
docs/plans/CLAUDE.md                          the pipeline contract
```

localStorage key: **`rphelper.workspace-layout`** (renamed from BookWriter's — must
not be copied verbatim).

## Stack

FastAPI + `pydantic-settings` · **SQLAlchemy Core (not the ORM)** · SQLite (one
file: rows + `sqlite-vec` `vec0` + FTS5) · React 19 + TS + Vite multi-entry ·
Mantine 7 (`core`/`hooks`/`tiptap`; **`form` present but unused, `notifications`
absent**)
· MobX 6 + `mobx-react-lite` · `react-router-dom` 7 · `@tabler/icons-react` `^3.40`
· TipTap + `tiptap-markdown` (edit) + `react-markdown` (render) · `@dnd-kit`
(available, unused) · SSE over POST · HttpOnly `SameSite=Lax` cookie · nginx +
uvicorn under `supervisord` in one container.

No Tailwind / CSS modules / styled-components. One `global.css` for resets.

## The four frontend entries

| Entry | Actor | Realizes |
|---|---|---|
| `bootstrap` | ACT-003, pre-database | FEAT-001 |
| `login` | unauthenticated | FEAT-002 |
| `admin` | ACT-001 | FEAT-003, FEAT-004, FEAT-005 |
| `app` | ACT-002 | FEAT-006..FEAT-017 |

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

- `BrowserRouter basename="/admin"`, same `AppShell` (`header` 56, `navbar` 220 /
  `sm`), **no `padding`** (pages bring `Container size="lg" py="md"`), no `aside`,
  no breadcrumbs, **flat `<Routes>`** (no `<Outlet/>`). Back-to-app is a real
  `<a href="/">`, not a router `Link`.
- **Gate:** `main.tsx` awaits `GET /api/me`, then mounts or redirects — nothing
  rendered meanwhile. Pure `resolveAdminAccess(currentUser)` + impure async
  `enforceAdminAccess()`. Deny cases: no session → `/login`; session but no
  resolvable user → `/login`; role not admin → `/`. **A 502/network failure is not
  a deny** (`deployment.md`).
  **Deviation:** BookWriter decodes a JWT pre-mount; impossible here — HttpOnly
  cookie **and** FEAT-003's disable-ends-sessions needs revocable server-side
  sessions.
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
spot) · create/edit is **always a `Modal`** · **`@mantine/form` NOT used** —
per-modal MobX `*Draft.ts` class (observable fields, `serverErrors`,
`submitStatus`, `clientErrors`/`errors`/`canSubmit` getters) with an **external**
`submitX(draft, …, onSaved, signal?)`, never a method · fresh draft per open via
conditional mount · modal open/target flags are component-local `useState` (view
state, not domain state) · **no toasts** (`@mantine/notifications` absent) —
success = modal closes + list refreshes · **never optimistic** — re-load after
every mutation, `void` + non-rethrowing catch · **confirm step** on disable
account / delete LLM connection / rebuild index (designed, not inherited; no AC
requires it) · page state = `makeAutoObservable` class **with no methods** + free
`loadX`/`xAction(state, …, signal?)` that `runInAction` and early-return on abort,
driven from `useEffect` + `AbortController`.

### Admin API facts

- `GET /api/me` → `{id, username, role}`; **401** when no session **or** the
  account no longer resolves (disabled — FEAT-003). Own identity only.
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
| **R3** | Memo state is one column, three values. Default on creation `searchable`. `forced` always in the system prompt and excluded from `memo_search`. **`disabled` reaches the assistant by NO path** — not context, not tools, not error payloads. **Constrains the assistant only: my-search DOES show `disabled` memos.** Memos never archive (FEAT-012, UC-042, UC-044, UC-052) |
| **R4** | **No silent model fallback.** Resolution yields a model *reference*, unvalidated; validation happens at **use time** against enabled models and raises typed `model_not_enabled` carrying which level set it. Never skip a disabled level and keep walking. Same for the embedding designation → `no_embedding_model` (FEAT-004, UC-012) |
| **R5** | **A `model → dependent sessions` query must not exist** on any admin surface — answering it discloses other users' sessions. "Are you sure? N sessions use this model" is a forbidden UI pattern, and **the LLM Servers page's confirm dialog is where it will be attempted**. Every read path scoped by owner **in the query** (FEAT-019, UC-012, UC-065, UC-066) |
| **R6** | Archive = out of the working list, never destroyed, always restorable. `archived_at` nullable, **no delete path** for characters/setups/sessions. No "finished" state (UC-019, UC-025, UC-068) |
| **R7** | Settling collapses the discussion; re-open allowed **only while nothing follows**; a settled discussion **never reaches the assistant again**. Deliberate asymmetry: a settled answer is editable forever (UC-029, UC-036, UC-037, UC-038) |
| **R8** | Translations are a success-only cache keyed `(entry, target language)`, in their own table, and **never enter context** (FEAT-011, UC-039, UC-041) |
| **R9** | The assistant's reach is **exactly three tools**. A failed tool is a tool *result* — the discussion continues. The assistant never writes into the session (ACT-004, UC-051, UC-053) |
| **R10** | The roleplayer's text is committed **before** any model call; a model failure loses nothing. An enormous paste warns but is **never refused** (UC-032, US-035.AC-2) |

## SSE frame protocol

```
token | tool_start | tool_result | tool_fail | error | done
```

- `done` mandatory on success; a stream ending without it = `llm_unreachable`.
- `error` and `done` mutually exclusive and terminal.
- **`tool_fail` is NOT terminal** (R9).
- `error` carries the same `{code, message, detail}` shape as JSON errors.
- `tool_result` carries a **summary**, never raw retrieved content.
- POST + JSON body → client uses `fetch()` + `body.getReader()` + `TextDecoder({stream:true})`, split on `"\n\n"`, keep the trailing partial frame. **Not `EventSource`** (GET-only).
- App sets `X-Accel-Buffering: no`; nginx also sets `proxy_buffering off`.

## Context assembly — what is in, what is out

**In:** resolved system prompt + character sheet + **forced** memos + RP-language
instruction + enabled tool descriptions; the session's entries (live, current
text); the **open** discussion's messages.

**Out, each with the rule that forbids it:** `searchable` memos (R3) ·
`disabled` memos (R3) · collapsed discussions (R7/UC-038) · translations (R8) ·
other users' material (R5) · other characters' sessions (UC-054).

## Search at a glance

| Surface | Arms | Scope | Notes |
|---|---|---|---|
| `memo_search` (FEAT-014) | vec + FTS, RRF | `user_id`, `state='searchable'`, the 4-level chain | excludes `forced` and `disabled`; works with no setup |
| `session_search` (FEAT-015) | **vec only — settled, no RRF step** | `user_id` **and** `character_id`, excl. current | semantic-only is a product decision (challenge C5); BM25 over `session_fts` would be a partner-name matcher — do not turn the FTS arm on. `session_fts` is kept for my-search. Reversible at low cost; flip condition in `overview.md` |
| my-search (FEAT-017) | vec + FTS, RRF per kind | `user_id`; 5 corpora | ACT-002 UI, **not** a tool; results grouped by kind, each jumps to its target. **Shows memos in all three states, `disabled` included** (R3 binds the assistant, not the owner) — mark disabled hits visibly |

Filter first (relational), then rank. `sqlite-vec` KNN is **exact** — no recall
tuning. RRF with `k = 60`, ranks only, no score normalisation. All three go through
one narrow port so the store is swappable (flip condition in `overview.md`).

Embeddings are written in the **same transaction** as the relational write. A memo
**state** change re-embeds **nothing** — that is the payoff of one store.

## Typed errors the SPA branches on

`model_not_enabled` (carries the level that set it) · `no_embedding_model` ·
`secret_ref_missing` · `llm_unreachable` · `tool_failed` · `translation_failed` ·
`discussion_not_resumable` · `already_configured` · `account_disabled`.

Wire shape: `{ "error": { "code", "message", "detail" } }`. `detail` never carries
another user's data, never carries counts derived from it, never carries a
`disabled` memo's body.

## UI geometry constants

**Aside width (A)** — right-anchored, `vw`, CSS custom property via one `autorun`
(zero shell re-renders): default `0.35`, min `0.15`, max `0.60`, keyboard step
`0.02`, 2-decimal rounding, handle `6px`/`col-resize`/`touchAction:none`, window
listeners **not** `setPointerCapture`, `ArrowLeft` widens. **`calc(var(...))`
wrapper is load-bearing — Mantine's `rem()` mangles bare comma-bearing strings.**
`AppShell transitionDuration = 0` while dragging.

**Answer-box height (B)** — delta-based (`startHeight + (startY - clientY)`, up
grows), plain MobX observable **not** a CSS var (the box already re-renders per
keystroke): min `64px`, default `96px`, max `0.5 × viewportHeight`, keyboard step
`24px`, handle `12px` flow child with `marginBlock:-3px` and a `pointer-events:none`
2px line. **Clamp: the lower bound wins on short screens.**

**(C)** The answer textarea does **not** auto-grow: `resize:"none"`, no `autosize`,
no `minRows`/`maxRows`, scrolls internally. `resize:none` keeps the native grip from
sitting under the Send icon.

All geometry + persistence in **one pure, DOM-free module**. Persistence: one
localStorage record, read is total and never throws (per-field fallback, clamped on
read), write is best-effort `try/catch` merging over a fresh total read, **once on
pointer-up**.

## Icons

`@tabler/icons-react` `^3.40`. `size={18} stroke={1.5}` main/header/composer,
`size={16}` inline, `size={14}` chevrons. Colour via the wrapping button's `color`.
**Every icon-only action goes through the shared `IconButton`** (`Tooltip` +
`ActionIcon` + `aria-label` from one `label` prop) — a deliberate deviation from
BookWriter, which has none. **Boundary:** `IconButton` governs toolbar / header /
composer / inline actions; **table rows use the overflow `Menu`** instead, so a row
holds exactly one icon-only control (the `IconDots` trigger, itself an
`IconButton`) and its actions are labelled menu items. Full icon table in
`ui-conventions.md`; note `IconCopy`
has no BookWriter precedent and is specified here because the clipboard is the
product's entire outbound boundary (UC-030).

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

## Open `_TBD:` items introduced by this doc set

| Where | What |
|---|---|
| `overview.md` | long RP eventually exceeds model capacity, unwarned (from `vision.md`); TLS if exposed beyond a LAN; no concurrency target stated |
| `data-model.md` | whether editing an entry discards its cached translation (design deletes; inference); what text represents a session for `session_vec`; whether characters/setups get FTS tables; import collision/id-remapping policy |
| `backend-structure.md` | **migrations vs registry-only create-if-missing** for schema evolution (the ORM question itself is now decided: SQLAlchemy Core) |
| `frontend-structure.md` | entry reordering not required by any requirement — do not build it |
| `ui-conventions.md` | `IconMessageCheck` for settle unvalidated; `IconLanguage` toggle-state presentation unspecified; no wider accessibility target stated; **no sorting/filtering/pagination assumes small cardinality — revisit on a large account or list count** |
| `admin-surfaces.md` | **connection-test result taxonomy is a proposal** (`reachable`/`unreachable`/`auth_failed`/`model_list_empty`) — no AC specifies one; **Sync and Seed** exist in the inherited drift report and are **required by no UC** — FEAT-005's planner decides, not the architect |
| `llm-and-streaming.md` | no tool-iteration cap stated; no `web_search` provider chosen |
| `search-and-retrieval.md` | RRF `k`/depth/result-count unmeasured; session re-embed policy; whether changing the embedding designation forces a rebuild; **how a `disabled` memo hit is marked in my-search results** |
| `deployment.md` | `64m` body limit is a judgement; no logging/metrics/alerting posture |

Resolved since the last pass, listed so nobody re-opens them: the **ORM choice**
(→ SQLAlchemy Core), **whether my-search shows `disabled` memos** (→ yes), and
**whether `session_search` gets a lexical arm** (→ no; it was already stated as a
decision but is now recorded as settled with a flip condition).

Not `_TBD:` but flagged for another owner: the my-search/`disabled`-memo decision
is a **requirements gap resolved at the architecture layer** and
**`/product-spec` should ratify it into FEAT-017's ACs**. The **confirm step** on
destructive admin actions is required by **no acceptance criterion** and
FEAT-003/004/005's planners may revisit it.
