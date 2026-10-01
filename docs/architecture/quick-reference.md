# Quick reference

Dense, agent-first index of `docs/architecture/`. Exempt from the doc-length
rule. Every line here is a pointer or a fact — the reasoning lives in the doc
named beside it. **Where this file and another doc disagree, the other doc wins.**

## Doc map — where to look for what

**Twelve docs.**

| Doc | Read it when you need |
|---|---|
| `overview.md` | System context, actor→surface map, the admin surface list, dev/prod topology, **the full stack decision list with rationale** (including the six post-first-pass decisions), the deferred list |
| `quick-reference.md` | This file — the index |
| `data-model.md` | Tables and columns, **snowflake identifiers**, **the one fixed-width timestamp form (+ its known `users` deviation)**, ownership/isolation columns, `users.role` + `users` as built (**+ `last_login_at`, stamped at session open**), `auth_sessions` as built (**+ where the bulk revoke lives**), **`llm_servers` / `models` as built (cascade, no `kind` CHECK, designation independent of `is_enabled`)**, **`sessions.model_ref` encoding `_TBD:`**, **drift as built by FEAT-005**, the merged `messages` table + its two views, **`sessions.model_ref` captured at creation**, archive semantics, `vec0` + FTS5 tables (**`session_vec`'s three sources**), drift registry, the export/import contract sketch + **the import policy** |
| `domain-rules.md` | **The role ladder + R1–R12, the cross-cutting invariants.** Read before touching any feature |
| `backend-structure.md` | FastAPI layout, routers/services split, `require_role`, **`roles.py` vs `dependencies.py` + what `require_user` resolves**, **the bootstrap route surface**, **the three admin route surfaces (`/api/admin/users`, `/llm-servers`, `/database`)**, **the 500 posture (`secret_ref_missing`, `schema_apply_failed`)**, **the first async code (`httpx.AsyncClient`) and its flip condition**, **the Sync rebuild's foreign-key posture**, **the authentication surface (login/logout/me, password hashing, session lifetime, token digest, cookie flags)**, **transactional DDL**, **SQLAlchemy Core**, `pydantic-settings`, the `"$ENV_VAR"` secret pointer, `app/ids.py`, **the JSON id boundary**, the stream routes, settle/re-open, the `(( ))` seam, the typed error model (**per-subclass `http_status`, the per-code status record, handler registration**), `/api/health` (**roll-up, all statuses 200**), the engine (**one `connect` listener, per-path engine cache, `get_connection`, loud `sqlite-vec` failure**), `/api/me`, the connection probe's two routes, **schema evolution (registry + admin-applied Alembic batch DDL)**, the logging call site, **the disconnect/stop path** |
| `frontend-structure.md` | Vite multi-entry (**`root: src/`, the `vite.config.ts` shape, the emitted layout**), the `admin` entry's boot + async gate + basename, **the `bootstrap` and `login` entries' boot shapes**, **pure-data-contract MobX stores (four rules) + where a store's file lives**, **the not-ready-yet predicate**, routing inside the `app` entry, **"ids are strings" and the test that enforces it**, the API client (**`ApiError` shape, the `client_*` codes, abort not wrapped**), the SSE consumer **and its abort path**, who imports the two stylesheets |
| `workspace-shell.md` | The `app` entry's one screen: the three columns, **all geometry**, the note wall's two modes, **layout persistence**, the stream, the ruler and the current zone, the kind switch and settle, **the stop control and the discard-empty-zone affordance**, the wall's contents, the character page, the user menu, the model picker, and the reversal record for the deleted splitters |
| `ui-conventions.md` | Everything that is **not** the shell: icons + the shared `IconButton` + the full icon table, the accessibility floor, tables, **the list/modal/MobX-draft/confirm CRUD conventions**, **no *success* toasts + the transient failure-notification rule**, never-optimistic, page state |
| `admin-surfaces.md` | The `admin` entry in full: 3 routes + 404, shell (**no user menu, no sign-out**), the admin gate and why it deviates, the Users / LLM Servers / Database pages — **each with its as-built state** (create-modal mapping, reset keeps sessions, Change Role = UC-087; no active column, probe ok-mapping, designation measures the dimension; the drift report's granularity, statuses, badge colours, Create/Sync postconditions, the views/virtual-table gaps) |
| `llm-and-streaming.md` | The one LLM client, resolve→validate→call, the SSE frame protocol, **the stop (UC-085) and its named divergences**, the tool loop (**no iteration cap**), context assembly and its exclusions, translation |
| `search-and-retrieval.md` | Hybrid vec+FTS+RRF, `memo_search`, `session_search` (**vector arm only**; `session_vec` spans **three sources**), my-search (**applies no reach-flag predicate**), embedding lifecycle + **the persona-edit fan-out**, rebuild |
| `deployment.md` | Ports, `start.ps1`, nginx directives (and the five deliberate deviations), **the open nginx seams (`/`, `/app/`, `/login`)**, compose (**the healthcheck asserts status, never body**), the `supervisord` ordering window and the admin boot, the single-generator guarantee, config conventions, **logging (loguru, two sinks, the redaction rule)** |

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

## Backend toolchain and packaging

- **One PEP 621 `backend/pyproject.toml`** holds runtime deps, dev deps and the
  `[tool.ruff]` / `[tool.mypy]` / `[tool.pytest.ini_options]` config. **No
  `requirements.txt`, no separate tool config files.**
- Virtualenv at **`backend/.venv`** via `uv venv`; dependencies installed with
  **`uv sync`**; **`uv.lock` committed**, regenerated by `uv sync`, never
  hand-edited. A new backend dependency goes into `pyproject.toml` and the lock is
  regenerated (`overview.md` — uv; `deployment.md` — the image installs from the
  lock).
- **Minimum Python 3.12.**
- **`sqlite-vec==0.1.9`**, pinned exactly; a failed load raises rather than
  handing out a connection without it (`backend-structure.md`).
- **`alembic` is a RUNTIME dependency** (plan 007) — batch DDL only. Its four
  negatives are verifier-checked: **no `versions/`, no revision chain, no version
  table, no startup upgrade**. Only `MigrationContext` + `Operations` +
  `batch_alter_table` (recreate mode) are used; nothing from `alembic.config`,
  `ScriptDirectory`, `EnvironmentContext` or `command.*`.
- **`httpx` is a RUNTIME dependency** (plan 006) — `httpx.AsyncClient`, the first
  outbound-HTTP and first async code in `app/`. The three network-reaching
  registry operations and their routes are `async def` over a **sync**
  `Connection`; flip condition in `backend-structure.md`.

## Configuration additions

- **`RPHELPER_LLM_REQUEST_TIMEOUT_SECONDS`** — default **30.0** (plan 006). The
  full `Settings` model is `backend-structure.md`'s.

## Backend test conventions

- **The database fixture is a real `.sqlite` file under pytest's `tmp_path`, one
  per test**, obtained through the same engine factory production uses. Not
  `:memory:` — that makes WAL a no-op and takes a different extension-load path,
  so it would silently not test the two properties `db/engine.py` exists to
  guarantee. Not a shared session-scoped database — that leaks DDL state between
  tests, which is precisely what FEAT-005's Sync does.
- **Environment isolation:** every `RPHELPER_*` variable and the settings
  accessor's `lru_cache` are cleared around each test.

## Frontend toolchain, packaging and tests

- **One `frontend/package.json`** — dependencies and four scripts (`build`,
  `test`, `typecheck`, `dev`); **`package-lock.json` committed**.
- **Two tsconfigs**: `tsconfig.json` (`strict`, `src/` + `tests/`) and
  `tsconfig.node.json` (`vite.config.ts`). No `paths` aliases (`overview.md`).
- **One `vite.config.ts` that also carries the Vitest block** — there is no
  `vitest.config.*`. The build is **rooted at `frontend/src`** and emits to
  **`frontend/dist`**; the Vitest block keeps **`frontend/`** as its root
  (`frontend-structure.md`).
- Test stack: **Vitest + Testing Library + jsdom**; `npm test` runs once and
  exits. **No ESLint, no JS linter** — `tsc --noEmit` is the gate.
- **Tests live under `frontend/tests/`, outside `src/`, mirroring it.**
  `frontend/tests/setup.ts` is harness source, not a test. Not co-located, for two
  reasons: the ids scan is scoped to `frontend/src`, so no fixture can trip it and
  no exclusion list is needed; and the build's root is `src/`, so nothing
  test-only is reachable from a bundle.

## Paths

```
backend/app/{routers,services,models,db}/     backend code (mypy target: app)
backend/app/ids.py                            the snowflake generator (not services/, not db/)
backend/app/roles.py                          Role enum + ROLE_LADDER + pure rung comparison; NO fastapi (db/schema.py imports it)
backend/app/dependencies.py                   CurrentUser, require_user, require_role(min_role), session-cookie set/clear
backend/app/services/passwords.py             the password-hashing seam (Argon2id, library defaults)
backend/app/routers/bootstrap.py              also declares require_unconfigured (its only consumer)
backend/tests/                                pytest target
backend/app/db/{schema,drift,sync}.py         registry / introspection / Alembic batch DDL; sync.py may import drift.py, never the reverse
backend/app/models/secret_ref.py              the "$"-pointer field type — a non-"$" value is FastAPI's 422, no domain code
backend/app/services/llm/client.py            httpx.AsyncClient; probe() + embed() only (no chat_stream yet); the 4-value probe-outcome set
backend/app/services/llm_registry.py          servers, models, the probe primitive, designation, both use-time validators (no call site yet — by design)
frontend/src/{bootstrap,login,admin,app}/     the four Vite entries
frontend/src/shared/                          api client, SSE consumer, IconButton, AppProviders, notifyFailure
frontend/src/shared/notReady.ts               the one not-ready-yet predicate (transport failure, or malformed body at >= 500); used by bootstrap AND the admin gate
frontend/src/shared/ConfirmModal.tsx          the one confirm component; cancel left of confirm (plan 005)
frontend/src/admin/                           gate, not-ready screen, shell state, nav table, shell, 404, app, page store, drafts — all beside main.tsx
frontend/src/<entry>/<page>State.ts, *Draft.ts   a single-entry store lives in its entry folder beside main.tsx
frontend/tests/                               Vitest target — outside src/, mirrors it
frontend/dist/{bootstrap,login,admin,app}/index.html   the emitted layout nginx resolves against
backend/pyproject.toml + backend/uv.lock      backend deps + tool config; lock committed
backend/app/logging.py                        loguru sinks + the InterceptHandler; called ONCE from main.py
frontend/src/global.css                       hand-written stylesheet 1 of 2 — resets only
frontend/src/shell.css                        hand-written stylesheet 2 of 2 — workspace layout only, imported by the `app` entry alone
data/rphelper.sqlite                          state 1 of 2; /app/data in prod
data/logs/rphelper.log                        state 2 of 2 — the rotating log sink (data/ is the only writable volume)
docs/product/                                 requirements — read-only
docs/product/quick-reference.md               the id registry
docs/architecture/                            this doc set
docs/plans/CLAUDE.md                          the pipeline contract
```

localStorage keys — two keys, two scopes, **never consolidated**:

| Key | Scope | Owner |
|---|---|---|
| **`rphelper.workspace-layout`** | the `app` entry only | `workspace-shell.md` (renamed from BookWriter's — must not be copied verbatim) |
| **`rphelper.color-scheme`** | all four entries | `overview.md` — Mantine's `localStorageColorSchemeManager`; both schemes, dark default |

Folding one into the other would make the login page's colour scheme depend on a
workspace record.

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
- **Import mints FRESH ids** and remaps the payload's internal references
  (US-136.AC-2). It does **not** preserve them — that earlier claim, and the
  collision check it implied, are withdrawn (`data-model.md`). Import uses the
  same generator as every other write.

**Flip condition:** the layout *and* the string boundary assume **exactly one
generator process per node id** (one container, one uvicorn — `deployment.md`). A
second worker or a syncing second instance re-opens both.

## Timestamps — one fixed-width text form

Every stored timestamp is UTC ISO-8601 **text**, **microsecond precision, explicit
`+00:00`** (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`) — because these columns are
compared **as text** (`auth_sessions.expires_at` on every request) and mixed forms
compare silently wrong (`data-model.md`). **Known deviation, not yet fixed:**
`users.created_at` / `updated_at` from plan 003 use plain `isoformat()`
(microseconds dropped when zero) — owned by a `/bug-fixer` pass against plan 003.

## Stack

FastAPI + `pydantic-settings` · **uv** (committed `uv.lock`) · **SQLAlchemy Core
(not the ORM)** · SQLite (one file: rows + `sqlite-vec` **`==0.1.9`** `vec0` +
FTS5) · **Alembic — batch DDL only, not a
migration framework** (no `versions/`, no version table, no startup upgrade;
`db/schema.py` is the source of truth and the admin drift page applies —
`overview.md`, `backend-structure.md`) · **`loguru`** (two sinks: console `DEBUG`
+ rotating file `WARNING` at `data/logs/`; the **`InterceptHandler` is
load-bearing** — without it uvicorn's output never reaches the file and nothing
errors; **absolute redaction rule at every level** — `deployment.md`) ·
React 19 + TS + Vite multi-entry ·
Mantine 7 (`core`/`hooks`/`tiptap`/**`notifications`**; **`form` is NOT a
dependency**; **`notifications` IS used — transient FAILURE reasons only,
`autoClose` 5000, no success toasts** (US-044.AC-4, reversing the old "absent"
note); **`AppShell` in the `admin` entry only** — the `app` workspace is a
hand-written CSS grid)
· MobX 6 + `mobx-react-lite` · `react-router-dom` 7 · `@tabler/icons-react` `^3.40`
· TipTap + `tiptap-markdown` (edit) + `react-markdown` (render) · **`@dnd-kit`
(used — note reorder only)** · SSE over POST · HttpOnly `SameSite=Lax` cookie over **server-side
`auth_sessions`** (opaque 32-byte token, stored as a SHA-256 digest, absolute 720 h)
· **Argon2id via `argon2-cffi`, library defaults** (passwords only) · **pysqlite
with transactional DDL** (`begin()` covers `CREATE TABLE`) ·
nginx + uvicorn under `supervisord` in one container.

No Tailwind / CSS modules / styled-components. **Exactly two hand-written
stylesheets:** `global.css` (resets only, every entry) and `shell.css` (the `app`
workspace's layout only — grid, `--navw` rail, the 820px media query; the `app`
entry alone). Everything else is Mantine (`frontend-structure.md` owns the
division; `workspace-shell.md` carries the same decision).

**TypeScript only — no JavaScript source.** Every authored file under `frontend/`
— components, stores, tests, and Node-side config such as `vite.config.ts` — is
`.ts` / `.tsx`. No `.js` / `.jsx` / `.mjs` / `.cjs`, no `allowJs`, no `checkJs`
(`overview.md` has the reason; the root `CLAUDE.md` holds the rule).

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

**Where it lives** (plan 004, superseding plan 003's "same module" proposal):
`app/roles.py` = enum + `ROLE_LADDER` + pure comparison, **no `fastapi`**
(`db/schema.py` imports it); `app/dependencies.py` = `CurrentUser`,
`require_user`, `require_role`, cookie writers. `require_user` resolves cookie →
digest → live, unrevoked, unexpired `auth_sessions` row → enabled `users` row →
**role read live**, so a role change or disable bites on the **next request**.
`require_unconfigured` lives in `routers/bootstrap.py`.

## Auth and bootstrap at a glance — `backend-structure.md`

| Route | Answers |
|---|---|
| `POST /api/bootstrap/create` | **201** + identity **+ `Set-Cookie`** (operator signed in, same transaction as `create_all` + admin insert); no token in the body; router-level `require_unconfigured` |
| `POST /api/bootstrap/import` | reserved — `fast/003.bootstrap-from-export` (UC-002 deferred) |
| `POST /api/auth/login` | **200** + identity + `Set-Cookie`; **never 401**; any failure = `invalid_credentials` **400**, uniform for unknown user / wrong password / disabled (US-006.AC-3) |
| `POST /api/auth/logout` | **204**, idempotent, **no `require_user`**, revokes the calling session only |
| `GET /api/me` | identity, or **401** `not_authenticated` (no/dead session, disabled account) |

- **Cookie:** name from `Settings.session_cookie_name` · `HttpOnly` · `SameSite=Lax`
  · `Path=/` · `Max-Age` = TTL · **`Secure` OFF** (no TLS; flip: TLS anywhere →
  on, one setter in `app/dependencies.py`). Cookie lifetime is a hint; the row's
  `expires_at` is the authority.
- **Lifetime:** `expires_at` written once from `session_ttl_hours` (720), **never
  moved**; **no refresh route, no sliding** (single writer — every read would
  become a write).
- **Token:** 32-byte `secrets.token_urlsafe`, stored as **SHA-256**, **deliberately
  not Argon2**; plaintext only in the cookie; never logged.
- **`users.password_hash`** = argon2-cffi's encoded string; params live in the
  value, no `hash_algorithm` column.
- **Entries:** `bootstrap` reads `/api/health`'s **`configured` alone** (a fresh
  instance is `degraded`/`missing` and that is correct), five states, hands off by
  document navigation to **`/`**; `login` makes **no request on mount**, renders
  every failure in place, goes to `/` for both roles, has **no disabled-account
  screen** and **no not-ready state**.
- **Not-ready-yet** = `client_transport_failed`, or `client_malformed_error` at
  status ≥ 500 (`shared/notReady.ts`); fixed 2000 ms re-probe, uncapped, plus a
  manual retry.

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
  a deny** (`deployment.md`). **Five boot outcomes** (plan 005): 401 → the shared
  client has already navigated, the gate navigates nothing; non-admin → `/`;
  admin → mount; **not-ready** (`shared/notReady.ts`) → re-probe every 2000 ms,
  navigates nothing; **anything else, incl. a well-formed 403 or 5xx** → failure
  panel + manual retry, navigates nothing (`frontend-structure.md`).
- **Header:** `Burger`, title, `<a href="/">` — **no user menu, so no sign-out in
  the admin area**; `ColorSchemeToggle` not mounted (both left to feature `008`).
- **Nav rows:** all three declared since plan 005; both former 404 targets now
  have pages (`006`, `007`).
  **Deviation:** BookWriter decodes a JWT pre-mount; impossible here — HttpOnly
  cookie **and** FEAT-003's disable-ends-sessions needs revocable server-side
  sessions.
- **Database page — `Create` and `Sync` are the schema-evolution mechanism.**
  Per-row, administrator-triggered, executed by `db/sync.py` via Alembic batch
  operations (SQLite cannot drop or retype a column in place). `Create` = UC-015's
  missing tables; `Sync` = an existing table whose shape moved. **Seed is not
  carried across** (`_TBD:`, no seed data exists — plan 007 looked and declined).
  Nothing runs at boot. **As delivered (plan 007): the report + per-row
  Create/Sync and nothing else** — Rebuild index (UC-016 / US-019) is owned by
  **`docs/plans/fast/002.vector-index-rebuild`**; Export / Import by features
  `030` / `031`; no disabled placeholders.
  - **Statuses (three, fixed):** in sync → **`green`**, drifted → **`yellow`**,
    missing → **`red`**; the status word is rendered as text, colour is redundant.
  - **Compared:** column set, declared SQLite type (compiled through the SQLite
    dialect), NOT NULL, index set keyed on (columns, uniqueness). **Not
    compared:** defaults, `CHECK` text, FK clauses. Implicit UNIQUE/PK indexes
    are not live indexes. No row count, size or timestamp.
  - **Create and Sync are idempotent and total** — no state precondition, no
    "wrong state" code. Create never drops anything. Each action is offered only
    in its state (**absent, not disabled**); an in-sync row has no trigger.
  - **Sync = recreate-mode rebuild:** surviving columns' data kept
    (US-018.AC-5); a **lossy** Sync names the lost columns and needs a confirm
    (US-018.AC-3/AC-4); a failed apply rolls back completely, no
    `_alembic_tmp_*` left (US-018.AC-6/AC-7). The cast refusal is a post-copy
    probe only for `INTEGER`/`REAL`/`NUMERIC`/`DECIMAL`/`BOOLEAN` targets.
  - **FK posture:** `foreign_keys = OFF` **outside** the transaction, rebuild,
    `foreign_key_check` before commit, `ON` restored on both paths (pooled
    connection; the pragma is ignored inside a transaction).
  - **Gaps, with owners:** views and `vec0`/FTS5 tables are outside the report
    (`metadata.tables` only) — the features introducing them extend it; once
    views exist, a Sync of a table a view references may fail safely at the
    rename until that feature handles views around the rebuild.
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
· **`@mantine/form` is NOT a dependency** — per-modal MobX `*Draft.ts` class
(**observable fields only** — `serverErrors`, `submitStatus`, no methods, **no
getters**) with **pure free functions** `clientErrors(draft)` / `errors(draft)` /
`canSubmit(draft)` and an **external** `submitX(draft, …, onSaved, signal?)`,
never a method
· fresh draft per open via conditional mount · modal open/target flags are
component-local `useState` (view state, not domain state) · **no *success* toasts** — success = modal closes + list refreshes; **`@mantine/notifications` IS a dependency and IS used, for transient FAILURE reasons only** (`autoClose` 5000: `llm_unreachable`, `model_not_enabled`, `translation_failed`, `tool_failed` and the rest of the typed table, **only where the failure is not already rendered in place**). **Reviewable boundary: a notification whose message is a success is a defect.** US-044.AC-3's **retry lives in the stream at the failed exchange**, not in the notice, which auto-dismisses ·
**never optimistic** — re-load after every mutation, `void` + non-rethrowing catch
(the workspace narrows the re-load to the edited row, same intent) · **confirm
step** via **`shared/ConfirmModal.tsx`** (cancel left of confirm) on disable
account / delete LLM connection / **clear embedding** (US-015.AC-2) / **a lossy
Sync, only when a column will be dropped** (US-018.AC-3/AC-4) / rebuild index
(**not yet realized** — `fast/002`); **not** confirmed: re-enable, saving an
enabled-model set, `Create`. A confirm **may name structure** (table, column,
index columns, type) and **never content** — no "N rows will be lost", "N rows
will be rebuilt", "rows affected" ·
**a probe-backed picker gets its selection from the list payload, never from the
probe** — failed-probe resilience by construction, one shared picker module · page state = `makeAutoObservable` class **with no
methods** + free `loadX`/`xAction(state, …, signal?)` that `runInAction` and
early-return on abort, driven from `useEffect` + `AbortController` ·
**pure data contracts everywhere** (`frontend-structure.md`'s four MobX rules):
a MobX class holds observable fields only — **no methods, no computed getters** —
derivations are pure free functions, effects are free functions with an optional
`AbortSignal` · notifications: outlet in **`shared/AppProviders`** (`autoClose`
5000 on the outlet), raised **only** via **`shared/notifyFailure(thrown)`** — no
success path, no colour parameter · `IconButton`: `ActionIcon` variant
**`"subtle"`**, `sizeVariant` defaults to `"main"`, props never widened.

### Admin API facts

**Route surfaces** (`backend-structure.md`) — all under `/api/admin/`,
`require_role(Role.admin)` once per router (all three consumers now exist), ids in
paths use the `models/ids.py` inbound alias:

| Prefix | Routes |
|---|---|
| `/api/admin/users` (plan 005) | `GET`, `POST` (201), `POST /{user_id}/{disable\|enable\|password\|role}` — named actions, not one `PATCH`; no query params |
| `/api/admin/llm-servers` (plan 006) | `GET` (rows carry enabled model names), `POST` (201), `PATCH /{server_id}`, `DELETE /{server_id}` (204), `POST /{server_id}/test`, `GET /{server_id}/available-models`, `POST /{server_id}/models` (replace set; POST not PUT), `POST` / `DELETE /{server_id}/embedding-model` |
| `/api/admin/database` (plan 007) | `GET /tables`, `POST /tables/{table_name}/create`, `POST /tables/{table_name}/sync` — all 200, no body, no query; apply answers the re-derived row; `{table_name}` resolved **in `db/sync.py`**, never interpolated; no ids on this wire |

- `GET /api/me` → `{id, username, role}`, **`id` a decimal string**; **401** when
  no session **or** the account no longer resolves (disabled — FEAT-003). Own
  identity only. Three consumers: the admin gate, the app's user menu (UC-071,
  US-093), and sign-out.
- **Users:** **last login** = `users.last_login_at` (em dash when NULL), stamped
  in the open-session transaction, `updated_at` not bumped. **A password reset
  keeps live sessions** (US-010.AC-3). **Change Role = UC-087 / US-140**; self
  target → `self_role_change_refused` 409 on the modal's general key; the action
  is not hidden on one's own row. Create modal: 409 → username field; the
  password-policy mapping is **pending a policy**, not missing.
- **Two** routes over **one** probe primitive: list-available-models (UC-012/013)
  and **test connection** (UC-011, own typed result). **Test answers 200 even for
  a failing outcome** and writes `llm_servers.last_test_*`; **available-models
  writes nothing and answers 502 `llm_unreachable`**. A failed test never blocks
  registration. **Probe outcomes `reachable`/`unreachable`/`auth_failed`/`model_list_empty`**
  — kept at four by plan 006; ok = `reachable` only; `last_test_error` stores the
  value itself; declared once in `services/llm/client.py`.
- **No "active" column or switch** on LLM Servers. **Designation measures the
  dimension** with one real embeddings call; a model that cannot embed is
  refused, nothing saved (US-015.AC-3/AC-4). **Clear Embedding is confirmed**
  (US-015.AC-2), row menu only. Designation is independent of `is_enabled`; the
  use-time validator needs both.
- **Rebuild index (UC-016) is ALWAYS available** — no precondition beyond
  authentication, never gated on drift state or on an embedding model being
  designated. With no designation it **runs and fails** `no_embedding_model`;
  availability and outcome are different things. The confirm step may stay. **No
  CLI script** — so the remedy needs a running app (`deployment.md`).
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
| **R1** | **The two chains share NO level.** Model / system prompt / tools inherit **`character → session`** — there is **no user-level default** (UC-050's postcondition); RP language + preferred language inherit `user → session`, **skipping character**. **Corrected:** this line and R1's diagram previously read `user → character → session` for the first chain, which was always wrong. Schema-enforced on both sides — `characters` has no language columns, `users` has no model/prompt/tools columns (FEAT-013, UC-047, UC-048, UC-050) |
| **R2** | Memo chain is a **union** over user + character + setup? + session. With no setup it degrades to user+character+session **with no gap** — same query, one fewer OR-term. No sentinel setup row (FEAT-007, UC-046) |
| **R3** | A note's reach is **two independent booleans, `is_enabled` and `is_forced`** — not one three-valued column. Defaults `is_enabled = true`, `is_forced = false`. Disabling **preserves** `is_forced`, so re-enabling restores the mode (US-101). **`is_enabled` gates first; `is_forced` is consulted only afterwards** — selecting on `is_forced` alone prompts a disabled forced note, the exact leak the split made expressible. `NOT is_enabled` reaches the assistant by **NO path** — not context, not tools, not error payloads. **Constrains the assistant only: my-search applies neither flag.** Order is a third axis (`sort_key`, within a level). Memos never archive (FEAT-012, UC-042, UC-044, UC-045, UC-052, UC-075) |
| **R4** | **No silent model fallback.** Resolution yields a model *reference*, unvalidated; validation happens at **use time** against enabled models and raises typed `model_not_enabled` carrying which level set it. Never skip a disabled level and keep walking. **The MODEL is captured at session CREATION** onto `sessions.model_ref` (UC-050 step 2, US-059.AC-1, US-139) — **not on first compose**, which is what this line used to say — and a character configured with a model afterwards reaches **only sessions created from then on** (US-139.AC-1/AC-2). US-106's "first enabled model" floor is resolved at creation. **The SYSTEM PROMPT and TOOLS keep resolving LIVE** `character → session` for every session, old or new. **The split is deliberate — harmonising it either way is a defect.** Same no-fallback rule for the embedding designation → `no_embedding_model` (FEAT-004, FEAT-013, UC-012, UC-050) |
| **R5** | **A `model → dependent sessions` query must not exist** on any admin surface — answering it discloses other users' sessions. "Are you sure? N sessions use this model" is a forbidden UI pattern, and **the LLM Servers page's confirm dialog is where it will be attempted**. Every read path scoped by owner **in the query** (FEAT-019, UC-012, UC-065, UC-066) |
| **R6** | Archive = out of the working list, never destroyed, always restorable. `archived_at` nullable, **no delete path** for characters/setups/sessions. No "finished" state. Memos are the contrast: they do not archive (UC-025, UC-067, UC-068) |
| **R7** | Settling **buries** the group under the settled head; re-open is allowed **only while the current zone below is empty**; a buried group **never reaches the assistant again**, then or later. Deliberate asymmetry: a settled turn is editable forever and the assistant reads the current version (UC-029, UC-036, UC-037, UC-038, UC-078) |
| **R8** | Translations are a success-only cache keyed `(message, target language)`, in their own table, and **never enter context**. Only settled rows are translatable — in practice only `kind='partner'` (FEAT-011, UC-039, UC-041) |
| **R9** | The assistant's reach is **exactly three tools**. A failed tool is a tool *result* — the exchange continues. The assistant never files anything into the record (ACT-004, UC-051, UC-053) |
| **R10** | The roleplayer's text is committed **before** any model call; a model failure loses nothing, and the `accepted` frame makes that observable. An enormous paste warns but is **never refused** (UC-032, US-035.AC-2) |
| **R11** | **The ruler: settle is the only door into the record**, with one exception — a pasted partner block, born settled (US-121). The **current zone is a set, not a row** (`related_to IS NULL AND settled_at IS NULL`), so US-125 needs no constraint. Re-open is settle's exact inverse, gated on an empty zone, and applies only to a head that **has** a buried group — otherwise `nothing_to_reopen`. **Raw `messages` is touched by exactly two operations, settle and re-open**; every other reader goes through the `settled_entries` / `current_zone` views. **Settling never requires an assistant answer** (US-135) and **abandoning an empty zone is frontend-only — no route, no backend surface, R11 unchanged** (UC-086, US-134); the two are a pair closing an inescapable state (FEAT-009, FEAT-010, UC-035, UC-037, UC-083, UC-086) |
| **R12** | `(( ))` is **parsed once, at settle, and stored text is never re-parsed.** Wholly parenthesised → `kind='decision'`; a fragment inside a draft is stripped from the head row in the same transaction and is not preserved. **Partner text gets no special treatment.** Three layers: server decides, system prompt instructs the model, client previews and is never authoritative. **Recorded constraint, no longer a `_TBD:`**: the convention assumes double parentheses never occur in the roleplayer's own RP prose — examined and confirmed by the roleplayer (US-130's `Constraint:` line). Flip condition: if one ever does, settle silently drops it and an escape mechanism becomes necessary (UC-081, UC-084, US-129, US-130, US-131) |

## SSE frame protocol

```
accepted | token | tool_start | tool_result | tool_fail | error | done
```

- **`accepted` is emitted once, before the first `token`**, and carries the
  **roleplayer's** committed zone row id — so an in-place edit of a just-sent
  message can `PATCH` without waiting for a reload (US-115). It makes R10's
  ordering observable and arrives on the failure path too.
- `done` mandatory on success and carries the **assistant's** row id. **Both ids
  are decimal strings.**
- **A stream ending without `done` is NOT always `llm_unreachable` — corrected.**
  A stop (UC-085) is a **fourth** way a stream ends, beside `done`, `error` and an
  unexpected close, and the server emits nothing for it. **The client knows it
  aborted** (its own `AbortController`), so it must **not** surface
  `llm_unreachable` for a stop it initiated; it reloads the zone instead. The
  server cannot tell a stop, a network drop and a closed tab apart and
  deliberately does not try (`llm-and-streaming.md`, `frontend-structure.md`).
- **The stop is `controller.abort()` on the existing `fetch()`. No stop route, no
  registry of in-flight work. No new frame.** The server persists the partial
  assistant text as an ordinary current-zone row and unwinds (US-132.AC-1);
  stopping mid-tool-call **ends the exchange** and the candidate may be empty.
- `error` and `done` mutually exclusive and terminal — of the terminations the
  *server* produces.
- **`tool_fail` is NOT terminal** (R9).
- `error` carries the same `{code, message, detail}` shape as JSON errors.
- `tool_result` carries a **summary**, never raw retrieved content.
- Frames are built in one place, `services/llm/frames.py`.
- One streaming route: **`POST /api/sessions/{id}/zone/compose`**. Its
  non-streaming sibling `POST /api/sessions/{id}/zone/messages` makes no model
  call and returns JSON.
- POST + JSON body → client uses `fetch()` + `body.getReader()` + `TextDecoder({stream:true})`, split on `"\n\n"`, keep the trailing partial frame. **Not `EventSource`** (GET-only).
- App sets `X-Accel-Buffering: no`; nginx also sets `proxy_buffering off`.
- **No tool-iteration cap** (FEAT-010, FEAT-014/015/016) — the stop bounds a
  runaway loop, because the loop dies with the socket. That earlier `_TBD:` is
  closed.
- **Two named divergences from `docs/product/`, pending amendment:**
  **US-133.AC-1** (a stopped tool call will **not** let the discussion continue —
  the exchange ends) and **US-133.AC-2** ("nothing is cached" on a stopped
  translation is **best-effort only** — one `await request.is_disconnected()`
  check before the cache write, not a guarantee). Do not design to either as
  written (`llm-and-streaming.md`).

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
| `session_search` (FEAT-015) | **vec only — no BM25, no RRF step** | `user_id` **and** `character_id`, excl. current | semantic-only is a product decision (challenge C5); BM25 over `session_fts` (`title`, `partner_label`) would be a partner-name matcher — do not turn the FTS arm on. `session_fts` is kept for my-search. Reversible at low cost; flip condition in `overview.md`. **`session_vec` spans THREE sources (US-138): settled entries (`settled_entries`, still including decisions — US-122.AC-2) + the character's persona + the setup text.** That earlier `_TBD:` is closed |
| my-search (FEAT-017) | vec + FTS, RRF **within each kind** | `user_id`; 5 corpora (characters, setups, sessions, entries, memos) | ACT-002 UI, **not** a tool; grouped by kind, each hit jumps to its target. **Applies no `is_enabled`/`is_forced` predicate at all** (R3 binds the assistant, not the owner) — **ratified by US-137**, no longer an architecture-layer gap. A disabled hit is marked as disabled (US-137.AC-2); **how** it is marked stays open. Its entry corpus is the **`settled_entries`** view |

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

**NEW — the persona-edit fan-out, the system's first one-to-many invalidation.**
Because `session_vec` now includes the persona and the setup (US-138), **editing
a character's persona (or a setup) invalidates EVERY session vector under that
character**. It is **re-embedded inline, in the same transaction**, so search is
never stale — at a cost stated honestly: **N sessions = N embedding calls inside
one request**, and the edit is as slow as that takes. **Flip condition:**
mark-stale-plus-rebuild (a staleness marker + UC-016), one decision away.

**The deliberate write asymmetry, now with a third member on the fail-hard
side:** a memo create/body edit **and a character persona / setup edit** with no
embedding model **fail the whole transaction**; a message edit / settle /
re-open **succeeds, degraded** (US-112 — the record must not be blocked by an
instance-level omission). The line is **authoring act vs record-keeping**, not
which table. Do not harmonise the two.

**Changing the embedding designation neither forces nor prompts a rebuild**
(UC-013's postcondition) — existing vectors came from the superseded model, are
not comparable, and **nothing indicates this**. Remedy: UC-016, always available.
That earlier `_TBD:` is closed.

## Typed errors

Wire shape: `{ "error": { "code", "message", "detail" } }`. Full table in
`backend-structure.md`.

`model_not_enabled` (**409**; carries server id as a string, model name, and the
level — `character` | `session`) · `no_embedding_model` (**409**) ·
`secret_ref_missing` (**500**) · `llm_unreachable` (**502**) · `tool_failed` (a
tool *result*, not a stream error) · `translation_failed` ·
**`username_taken`** (**409**) · **`user_not_found`** (**404**) ·
**`self_role_change_refused`** (**409**, UC-087 / US-140.AC-2) ·
**`llm_server_not_found`** (**404**) · **`unknown_table`** (**404**) ·
**`schema_apply_failed`** (**500**; `detail` = table + `create`|`sync`, **never
the driver's message**) · **`zone_empty`** (settle with nothing in
the zone) · **`zone_not_empty`** (re-open while the zone is not empty) ·
**`nothing_to_reopen`** (the head has no buried group — a pasted partner block) ·
**`message_not_editable`** (edit targets a buried row) · `already_configured`
(**409**; carries a default non-empty `message` on the subclass) ·
**`invalid_credentials`** (**400, never 401** — the client's 401 navigation
would wipe the login message; uniform across unknown user / wrong password /
disabled, US-006.AC-3) · **`not_authenticated`** (**401**) ·
**`insufficient_role`** (**403**; names neither role).

**`account_disabled` is struck** — nothing raises it (plan 004); FEAT-003 may
reintroduce it if an administrator surface needs a distinguishable code.

**`http_status` is a class attribute each `DomainError` subclass sets**, decided
by the feature introducing the code; the error table has no status column by
design, and statuses live in `backend-structure.md`'s per-code status record. One
handler on the base class, installed by `errors.py`'s
`register_exception_handlers(app)` from the app factory. `BackwardsClockError` and
`ExtensionLoadError` are **not** `DomainError`s — operational 500s.

**The 500 posture** (user decision H1, `backend-structure.md`):
`secret_ref_missing` and `schema_apply_failed` are **one deliberate posture** —
nothing about the request is malformed; the instance failed to do what it
offered, or its environment is misconfigured (fixable only by changing the
environment and restarting). Both render as a failure panel. **Flip:** an admin
surface needs either as an actionable, field-level message → that code moves to a
4xx. A non-`$` secret pointer is **FastAPI's 422**, not a domain code.

**`/api/health` `schema` precedence: `missing` > `drift` > `ok`** — `"drift"` is
now produced (plan 007); the roll-up is one word naming no table; the probe runs
the PRAGMA walk (flip: narrow to presence if it shows against the healthcheck
interval); **caching it is rejected**.

**Frontend: call sites branch on `ApiError.code`** — never on `status`, never on
the message (`frontend-structure.md`). **`client_malformed_error`** (non-2xx
without a well-formed envelope; real status) and **`client_transport_failed`**
(`fetch` rejected; status `0`) are **client-side codes no backend produces**. An
abort is not an error and is not wrapped.

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

`@tabler/icons-react` `^3.40`. `size={18}` main/header/composer, `size={16}`
inline, `size={14}` chevrons — **`stroke={1.5}` on all three** (one family, one
visual weight). Colour via the wrapping button's `color`.
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
  disabled once the zone is non-empty (US-128). **The discard-empty-zone
  affordance (UC-086, US-134) follows the same precedent** — absent, not
  disabled, once the zone holds anything; glyph `_TBD:`.
- **`IconPlayerStop` REPLACES Send while a generation streams** — same slot,
  never both, because one is always inert otherwise (UC-085,
  `workspace-shell.md`). Settle is unaffected and stays put.
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
**The catch-all `/` is an open seam** — the build emits no `dist/index.html`, so
something must bridge `dist/app/index.html` to the root; unchosen, owned by
`fast/001.dev-and-container-harness` (`deployment.md`). **Same owner, two more:**
the **`location /app/` block** serves a URL space the root-mounted `app` entry
never uses; and **`/login` without a trailing slash** — the exact target of the
client's 401 navigation and the bootstrap refusal link — does not match
`location /login/` and falls to the unbridged catch-all.

**Healthcheck:** `curl -f` asserts the **HTTP status, never the body** —
`/api/health` is 200 whatever the roll-up says, so a fresh `degraded` instance is
healthy. A body-inspecting "hardening" makes the bootstrap page unreachable.

## Deferred / non-goals

- FEAT-018's four export granularities in full detail — contract sketched in `data-model.md`.
- FEAT-016's `web_search` provider adapter — **seam only**.
- **FEAT-002 deliberately does not build** (`overview.md`): session refresh /
  sliding expiry; rate limiting, lockout, attempt counting; "remember me";
  password reset / change-password (FEAT-003's); **rehash-on-verify (owned by no
  feature)**; session listing / sign-out-everywhere.
- **Context compaction — an explicit non-goal, and no longer a `_TBD:`**
  (`vision.md`, restated in FEAT-009 and FEAT-010). Context grows forever;
  nothing warns first; a context-window refusal arrives as an ordinary generation
  failure whose reason is shown (US-044). Decided, not open — the reasoning stays
  visible in `overview.md` and `llm-and-streaming.md` because a planner still
  needs it.
- **TLS** — HTTP-only posture inherited.
- **Metrics and alerting** — unspecified. Logging **is** specified
  (`deployment.md`).
- **Abandoning a current zone is NO LONGER here.** It is **resolved** — UC-086 /
  US-134 / US-135, frontend-only, no route, R11 unchanged. See `overview.md`'s
  decision 6, `workspace-shell.md` and `backend-structure.md`.

## Open `_TBD:` items across the doc set

| Where | What |
|---|---|
| `overview.md` | TLS if exposed beyond a LAN; no concurrency target stated; metrics and alerting unspecified |
| `data-model.md` | **whether `vec0` handles sparse snowflake rowids as efficiently as dense ones — verify before FEAT-014/FEAT-015 are planned**; whether editing a non-partner settled message discards its cached translation (design deletes; inference beyond US-111); whether characters/setups get FTS tables |
| `domain-rules.md` | **R4 — what session creation does when NO model is enabled at all: refused, or created with a NULL `model_ref` filled on first successful resolution. NEW, raised for `/product-spec`** (US-107 covers *sending*, not *creating*) |
| `backend-structure.md` | whether UC-080's first message should also draw an assistant reply (changes the response media type — FEAT-008's plan must settle it) |
| `frontend-structure.md` | where the archive toggle sits now that the character and session lists are gone (placement, not design) |
| `workspace-shell.md` | whether the character page's composer carries the kind switch or a setup choice (UC-080/US-117 decide neither); US-120's product `_TBD:` on what a settled **decision** does to the kind switch's alternating default, carried forward |
| `ui-conventions.md` | the wall pin and a note's "forced" flag are drawn with the **same pin glyph** for two unrelated meanings on one screen; the enabled/disabled note toggle's glyphs map onto no Tabler icon; the discard-empty-zone glyph; `IconLanguage` toggle-state presentation unspecified; no wider accessibility target stated; **no sorting/filtering/pagination assumes small cardinality — revisit on a large account or list count** |
| `admin-surfaces.md` | **Seed** exists in the inherited drift report and is **required by no UC** — RPHelper has no seed data at all, so it is recorded as prior art and not written up as a requirement; **FEAT-005's plan (007) looked and declined, without resolving it** (**Sync is no longer open** — it is Decision A's mechanism; **the connection-test taxonomy is no longer open either** — see the closed list) |
| `llm-and-streaming.md` | no `web_search` provider chosen |
| `search-and-retrieval.md` | RRF `k` / candidate depth / result count unmeasured; **how a disabled memo hit is marked in my-search results** (presentation only — the behaviour is ratified by US-137); **NEW — whether ARCHIVED sessions participate in the persona-edit re-embed fan-out, or are skipped and reconciled on restore**; **NEW — whether a persona edit touching many sessions needs a progress surface**; the **cost** of the per-write `session_vec` refresh on a long session; whether a per-session staleness marker earns a column |
| `deployment.md` | TLS / exposure model (the cookie's `Secure` flag is no longer part of it — shipped off with a flip condition); `64m` body limit is a judgement; **the `/` fallback — no `dist/index.html` exists, the mechanism bridging `dist/app/index.html` to the root is unchosen, owned by `fast/001.dev-and-container-harness`**; **same owner: the `location /app/` block vs the root-mounted `app` entry, and `/login` without a trailing slash** |
| `data-model.md` (conventions) | **not a design `_TBD:` but an open defect: `users.created_at` / `updated_at` deviate from the fixed-width timestamp form — `/bug-fixer` against plan 003** |
| `data-model.md` (`sessions`) | **the ENCODING of `sessions.model_ref`** — a bare model name is ambiguous across two servers; owned by FEAT-008 / FEAT-013's plans (the validator takes server id + model name separately) |

### Closed in THIS pass — do not re-open, do not re-list

Each item below was an open `_TBD:` (or a flagged-for-another-owner note) in this
doc set and is now **closed**. Re-adding any of them to the table above is a
regression, and a plan that treats one as unanswered is reading a stale copy.

| Was open | Now |
|---|---|
| **Observability posture** — no logging/metrics/alerting specified (`deployment.md`) | **Logging is specified**: `loguru`, two sinks, five `RPHELPER_LOG_*` settings, an absolute redaction rule at every level, `diagnose=False` on the file sink, and a recorded flip condition. *Metrics and alerting remain deliberately unspecified and are listed as an absence, not as this `_TBD:`.* |
| **`sessions.model_ref` after the character is configured with a model** (`data-model.md`, R4) | **Nothing happens — the session keeps its captured model** (US-139). Only sessions created from that point on capture the new one |
| **Tool-iteration cap** (`llm-and-streaming.md`) | **No cap** (FEAT-010, FEAT-014/015/016). The stop bounds a runaway loop — the loop dies with the socket |
| **Unbounded context growth, unwarned** (`overview.md`, `llm-and-streaming.md`) | **A recorded non-goal, not a question** (`vision.md`, FEAT-009, FEAT-010). Downgraded, not answered; the operational reality stays written down |
| **Abandoning a current zone without settling** (`overview.md`, `backend-structure.md`) | **Resolved: frontend-only** (UC-086, US-134, US-135). No route, no backend surface, **R11 unchanged** |
| **What text composes `session_vec`** (`data-model.md`, `search-and-retrieval.md`) | **Three sources** (US-138): settled entries incl. decisions + the character's persona + the setup text |
| **Import collision / merge-vs-empty-target policy** (`data-model.md`) | **Merges as new material; nothing existing is overwritten; imported ids arrive under fresh identity** (US-136). Mint new snowflakes, remap the payload's internal references |
| **Whether changing the embedding designation forces a rebuild** (`search-and-retrieval.md`) | **Neither forces nor prompts one** (UC-013). Stale vectors are not comparable and **nothing indicates it**; remedy is UC-016 |
| **R12 — double parentheses in RP prose** (`domain-rules.md`) | **A recorded constraint with its provenance** (US-130's `Constraint:` line): the convention assumes they never occur, confirmed by the roleplayer. Flip condition kept visible |
| **UC-011's connection-test taxonomy** (`admin-surfaces.md`) | **An authorized design proposal**, not an open question: UC-011 commits to two outcomes and calls a finer distinction "a design choice, not a requirement". The four values stay |
| **`secret_ref_missing`'s status posture** (`backend-structure.md`, finalization of plans 001..007, H1) | **500 kept**, as one shared posture with `schema_apply_failed`, reason and flip condition recorded once in the error model |
| **Whether Change Role realizes a product id** (`admin-surfaces.md`, plan 005) | **UC-087 / US-140** now specify it |
| **Whether a password reset revokes sessions** (`admin-surfaces.md`, plan 005) | **No** — now a requirement, US-010.AC-3 |
| **Whether my-search shows disabled memos** (`search-and-retrieval.md`, `overview.md`) | **Ratified by US-137** — it was already decided here and flagged for `/product-spec`; the flag is discharged. *How* a disabled hit is marked stays open |

**Newly open after this pass**, listed so they are found rather than rediscovered:
session creation with **no enabled model** (R4) · **archived sessions** in the
persona-edit re-embed fan-out · a **progress surface** for a long persona edit ·
(pre-existing, still open) how a disabled memo hit is marked in my-search.

**One product inconsistency flagged, not resolved:** **UC-012**'s exception flow
still says "no silent fallback up the `user → character → session` chain", naming
a user level for the model that **UC-050** and **UC-047** say does not exist. The
doc set follows UC-050 (the use case that owns resolution). No behaviour turns on
it — the prohibition is identical either way — but `/product-spec` should
reconcile the wording. Recorded in `domain-rules.md` R4.

**Closed in the previous delta — also do not re-open:** the `session_vec` refresh
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

Not `_TBD:` but flagged for another owner:

- **Two named divergences from `docs/product/`, pending amendment by
  `/product-spec`** — **US-133.AC-1** (a stopped tool call ends the exchange; it
  does **not** continue) and **US-133.AC-2** ("nothing is cached" is best-effort,
  not a guarantee). Recorded in `llm-and-streaming.md`. **Do not design to either
  AC as written.**
- The **confirm step** on destructive admin actions is architectural judgement
  except where an AC now requires it — **clear embedding (US-015.AC-2)** and **a
  lossy Sync (US-018.AC-3/AC-4)**. The rest may be revisited by a later planner.
- **Drift-report gaps with named owners** (`admin-surfaces.md`): SQL views and
  `vec0` / FTS5 tables are outside the report — the features introducing them
  extend it; a Sync of a view-referenced table may fail safely at the rename
  until the views feature handles it.
- **`memos`' orphan-scope check is not built** and is not part of the structural
  drift report — owned by the feature that creates `memos` (`data-model.md`).

*(The my-search/disabled-note flag that stood here is discharged — US-137
ratified it. See the closed table above.)*
