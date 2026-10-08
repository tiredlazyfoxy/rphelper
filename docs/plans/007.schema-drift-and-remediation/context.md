# Feature 007 — Schema drift and remediation · feature-wide context

## What this feature is

Gives ACT-001 the page on which the instance tells the truth about its own database
shape, and the two buttons that change it. The Database page reports, per table, whether
the live SQLite file matches what `db/schema.py` declares — in sync, missing, or drifted —
and offers a per-row `Create` for a table that does not exist and a per-row `Sync` for one
whose shape has moved. This is **the only path by which the schema ever changes**: there
is no migration history, no revision chain, no version table and no automatic upgrade at
startup, so a drifted table stays drifted until an administrator reads this page and
presses a button on that row.

The agreed boundary is `brief.md` in this folder — its Definition and its Scope In/Out
bound every step here and are **not** restated or widened. Read it first. Its two open
questions are closed by D1 and D7 below.

## Product ids

`FEAT-005`, via **UC-014** and **UC-015**, and **US-017.AC-1**, **US-018.AC-1**,
**US-018.AC-2**.

| Criterion | Where it lands |
|---|---|
| US-017.AC-1 (the report lists each table's status — in sync, missing, drifted) | `002` (the comparison and the registry walk), `004` (the report route), `005` (the rendered table and its badge) |
| US-018.AC-1 (remediation creates missing tables and brings drifted structures into sync) | `003` (the batch-operation executor), `004` (the two apply routes), `006` (the row actions) |
| US-018.AC-2 (the report afterwards reflects the corrected state) | `004` (each apply route answers with the freshly re-derived row), `006` (the never-optimistic re-load after every Create and every Sync) |

**UC-016 / US-019 — the vector-index rebuild — is NOT delivered here.** `brief.md` defers
it to `fast/002.vector-index-rebuild`, which has no vectors to rebuild until stage 004
creates the `vec0` tables. **No rebuild button, no rebuild route and no rebuild service is
written in this feature.** `006`'s `context.md` carries a stale cross-reference calling
UC-016 "feature `007`'s"; `brief.md` supersedes it and this plan follows `brief.md`.

**Also out, per `brief.md`:** the Export and Import controls that share this page
(FEAT-018, UC-061/UC-002) belong to features `030` and `031`. **The page ships with the
report table and its per-row actions and nothing else** — no header action bar, no
disabled placeholder for a later control.

**Related, cited but not delivered here:** the `memos` orphan-scope check
(`data-model.md` names it as part of FEAT-005's drift report) — `memos` does not exist
until feature `015`, so there is nothing to check; see D3 and `outcome.md`.

## Assumption every step rests on — what is built and what is only planned

`backend/` is built through **`001.backend-foundation`**; `frontend/` is built through
**`002.frontend-foundation`**. **`003.first-run-bootstrap`** is partly built;
**`004.authentication-session`**, **`005.admin-shell-and-users`** and
**`006.llm-server-connections`** are **planned, not built** — every row in their
`status.md` is `pending`. Build order is
`001 → 002 → fast/001 → 003 → 004 → 005 → 006 → 007`.

**Built and quotable today** (this feature reads these as they stand):

| Module | What this feature uses |
|---|---|
| `backend/app/db/schema.py` | module-level `metadata: MetaData`; every table is a `Table(...)` literal **in this file**; today it declares **`users` only** (9 columns; `id` is `BigInteger().with_variant(Integer(), "sqlite")`, `primary_key=True, autoincrement=False`; `username` `Text` `unique=True`; `role` a non-native `Enum`; **no explicit `Index(...)` objects anywhere**). Its docstring names feature `007` as the one that "walks `metadata.tables` directly" and states the module executes **no DDL ever, including at import**. **This feature adds no table and no column and does not edit this file.** |
| `backend/app/db/engine.py` | `get_connection` (the FastAPI dependency; opens **no** transaction — callers write `with conn.begin():` themselves), `get_engine`, `resolve_db_path`, `dispose_engines`, `ExtensionLoadError`. A `connect` event listener loads sqlite-vec, then sets `PRAGMA foreign_keys = ON` and `PRAGMA journal_mode = WAL`. **`foreign_keys = ON` is load-bearing for D8.** |
| `backend/app/errors.py` | `DomainError` (class attrs `code`, `http_status`; `to_wire()` → `{"error": {"code", "message", "detail"}}`), `register_exception_handlers` (the decorator form `app.exception_handler(DomainError)(handler)` is **deliberate** — mypy fails on `add_exception_handler` under the pinned FastAPI; **do not "fix" it**), and the handler that logs only `code`/`http_status`, never `detail`. |
| `backend/app/services/health.py` | `HealthProbeResult` (frozen dataclass: `status`, `configured`, `schema`) and `probe_health(connection, registry)`. Its own docstring says feature `007` adds the `"drift"` branch and that this is **a widening of the function, not a rewrite**. |
| `backend/app/models/health.py` | `HealthResponse`, `HealthStatus`, `SchemaState` — **`SchemaState` already declares `"drift"`** as a legal value; nothing produces it yet. |
| `backend/app/roles.py` | `Role(StrEnum)` with `ROLEPLAYER = "roleplayer"`, `ADMIN = "admin"`. A leaf module, no `fastapi` import. |
| `backend/app/routers/health.py` | the router house style: `APIRouter(prefix="/api", tags=[...])`; the **router** imports `metadata` from `app.db.schema` and passes it into the service; handlers return a pydantic model, never a bare dict; routers never `try/except` and never build an `HTTPException`. |
| `backend/app/routers/bootstrap.py` | the precedent for a **router-level dependency guard** declared at `APIRouter(..., dependencies=[...])` construction rather than per handler. |
| `backend/app/main.py` | `create_app()`; ordering `get_settings` → `configure_logging` → `FastAPI(lifespan=...)` → `app.state.id_generator` → `register_exception_handlers` → `include_router` lines. Collaborators imported as **bare names** on purpose (patchable test seams) — do not qualify them. Lifespan is `yield` and nothing else. |
| `frontend/src/shared/api.ts` | `apiGet` / `apiPost` / `apiPatch` / `apiDelete` over `apiRequest(path, method, body?, signal?)`; paths must start with `/api/`; a 401 triggers `documentNavigation.assign("/login")`. |
| `frontend/src/shared/apiError.ts` | `ApiError` with `.code` / `.status` / `.detail`, `isApiError`, and the synthetic `CLIENT_MALFORMED_ERROR` / `CLIENT_TRANSPORT_FAILED` codes. Failures are **thrown**, not returned as a union. |
| `frontend/src/shared/notifyFailure.ts` | the **only** module permitted to import `@mantine/notifications`; `frontend/tests/conventions.test.ts` asserts the importer list equals exactly `["src/shared/notifyFailure.ts"]`. |
| `frontend/src/shared/IconButton.tsx` | the only sanctioned icon-only control. |
| `frontend/src/shared/AppProviders.tsx` | the Mantine wrapper every entry and every component test uses. |
| `frontend/vite.config.ts` | four entries (`bootstrap`, `login`, `admin`, `app`); vitest configured **inside this file** (`environment: "jsdom"`, **`globals: false`**, `include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"]`). A separate `vitest.config.*` is forbidden. **This feature does not touch this file.** |

**Arriving with `004`/`005`/`006`, named by role and module path and never quoted as an
exact signature:**

- `backend/app/dependencies.py` (`004/002`) — `require_role(min_role)`, the dependency
  **factory**; `require_user`; and `CurrentUser`, a plain immutable value object carrying
  id, username and role (role read live from `users` every request). Precedence is always
  **401 before 403**. This feature attaches `require_role(Role.admin)` **once, at router
  level**.
- `backend/app/roles.py` gains `ROLE_LADDER` and a pure "is at least" predicate (`004/002`).
- `backend/app/routers/admin_users.py` (`005/003`) and `backend/app/routers/admin_llm.py`
  (`006/005`) — the admin-router precedent: the **whole path prefix on the `APIRouter`**
  (`/api/admin/users`, `/api/admin/llm-servers`), one service call per handler, **no query
  parameters anywhere**, no hand-mapped errors.
- `frontend/src/admin/AdminApp.tsx` (`005/005`) — the flat four-element `<Routes>`
  (`/`, `/llm-servers`, `/database`, `*`). **`/database` renders `NotFoundPage` today and
  this feature replaces exactly that one route element**, the way `006/006` replaced
  `/llm-servers`'s.
- `frontend/src/admin/navItems.ts` (`005/005`) — **already declares the `Database` /
  `/database` / `IconDatabase` row.** This feature adds no nav entry and **must not touch
  this file**.
- `frontend/src/shared/ConfirmModal.tsx` (`005/006`) — the one shared confirm dialog: open
  flag, title, a one-sentence consequence, the confirm button's label, an optional confirm
  colour (`red` for a destroy), an optional in-progress flag, cancel and confirm callbacks;
  cancel sits left of confirm. It holds no state and knows nothing about the domain.
  **Reused as-is, never hand-rolled.** Its open flag and its target row are
  **component-local `useState`**, never store fields.
- `frontend/src/admin/llmServersPageState.ts` + `LlmServersPage.tsx` (`006/006`) — the
  worked example of the page-state shape this feature mirrors.

**No step here quotes an exact signature for anything `003`, `004`, `005` or `006`
delivers.** Borrowed interfaces are named by role and module path; the skeleton agent
resolves the exact names against the delivered code. If the delivered code contradicts
what a step assumes, that is a **skeleton hand-back**, not something a coder improvises
around.

## Commands

From the root `CLAUDE.md`:

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

No step may leave the tree failing `mypy app` or `tsc --noEmit`.

## Architecture this binds to

- `docs/architecture/admin-surfaces.md` — **"Database page — FEAT-005 + FEAT-018's admin
  half" in full** (the report shape, the `Sync` authorization, the "no CLI alternative"
  paragraph, the `seed-missing` `_TBD:`, the scope-discipline paragraph), plus the shell
  section, the nav table, and **"Backend gating is independent and authoritative"**.
- `docs/architecture/backend-structure.md` — Layout (`db/drift.py`, `db/sync.py`,
  `routers/admin_db.py`), **"Schema evolution — the registry is the truth, the
  administrator applies"** with its four explicit negatives, the error model and its named
  error table, **`/api/health`**, routers-versus-services, "Authorization as router
  dependencies", Database access / SQLAlchemy Core.
- `docs/architecture/data-model.md` — **"Schema drift and rebuild"**, plus the `users`
  table (the only table the registry declares today) and the Identifiers section (for why
  this feature's wire carries no id at all).
- `docs/architecture/ui-conventions.md` — tables; row-action menus and the icon boundary;
  no sorting, filtering or pagination; loading, errors and empty states; async feedback;
  **mutations are never optimistic**; **the confirm convention**; page state; the
  accessibility floor.
- `docs/architecture/domain-rules.md` — **R5**.
- `docs/product/use-cases/FEAT-005.database-consistency.md`,
  `docs/product/stories/FEAT-005.database-consistency.md`.

Cited, never copied. Where a step needs a declaration an architecture doc gives verbatim,
the step's context points at the section and the skeleton agent reproduces it.

## Files this feature touches

```
backend/
  pyproject.toml                    # alembic -> runtime dependencies            (003)
  app/
    db/drift.py                     # NEW — the report value types + the two
                                    #   shape readers                            (001)
                                    # + the comparison and the registry walk     (002)
    services/health.py              # + the "drift" branch                       (002)
    errors.py                       # + 2 subclasses                             (003)
    db/sync.py                      # NEW — the Alembic batch-operation executor (003)
    models/admin_db.py              # NEW — request/response models              (004)
    routers/admin_db.py             # NEW — the guarded router                   (004)
    main.py                         # + one include_router line                  (004)
frontend/
  src/
    admin/AdminApp.tsx              # the /database route element replaced       (005)
    admin/databasePageState.ts      # NEW — the page store + its effects    (005, 006)
    admin/DatabasePage.tsx          # NEW — the report table and the row menu
                                    #   and the lossy-sync confirm          (005, 006)
```

**Not touched, and a step that touches one is out of scope:**
`backend/app/db/schema.py` (**this feature adds no table and no column**),
`backend/app/db/engine.py` (the PRAGMAs and the connection dependency are used as they
stand), `backend/app/config.py` (**no new setting**), `backend/app/ids.py` and
`backend/app/models/ids.py` (**no id crosses this feature's wire at all** — the report is
keyed on table names), `backend/app/roles.py`, `backend/app/secrets.py`,
`backend/app/models/health.py` (`SchemaState` already declares `"drift"`),
`backend/app/routers/health.py` (the roll-up widens inside the **service**; the router is
unchanged), `frontend/src/admin/navItems.ts` (`005` already declares the `Database` row),
`frontend/src/admin/main.tsx`, `frontend/src/admin/AdminShell.tsx`,
`frontend/src/admin/index.html`, `frontend/src/shared/*` (every shared module this feature
needs already exists or arrives with `005`), `frontend/src/global.css`,
`frontend/src/shell.css`, `frontend/vite.config.ts`,
`frontend/tests/conventions.test.ts` (see "Cross-cutting constraints").

**Out of scope, per `brief.md`:** the vector-index rebuild (`fast/002`), Export (`030`),
Import (`031`), the `memos` orphan-scope check (`015` at the earliest).

## Cross-cutting constraints every step holds

**R5 — the report carries no row count, anywhere, in any form.** No per-table row count
column, no "N rows" in a confirm sentence, no "N rows affected" in an apply response, no
`SELECT COUNT(*)` in `db/drift.py`, `db/sync.py`, `routers/admin_db.py` or the page. A row
count for `characters`, `sessions`, `messages` or `memos` is a count over every user's
material, and `domain-rules.md` R5 plus `admin-surfaces.md`'s Users-page rule forbid
exactly that shape. The forbidden strings, named so a reviewer can grep for them:
**"1,204 rows"**, **"N rows will be rebuilt"**, **"N rows will be lost"**, **"rows
affected"** — and every variant. A drift table is precisely where someone adds one in good
faith, which is why it is written out here rather than left to care.

**What the report *may* name is structure, never content.** A table name, a column name,
an index's column list and a SQLite type are **administrative data** — they are what
`db/schema.py` declares, they are identical on every instance, and UC-014 is unanswerable
without them. That is why the lossy-sync confirm may name the columns it will drop (D7)
and may never name how much is in them.

**Diagnosis cannot write; remediation is never reached by a read path.**
`backend-structure.md` states the reason for the `db/drift.py` / `db/sync.py` split
outright: *"the code path that only reports cannot write"*. Mechanically: `db/drift.py`
issues `PRAGMA` reads and `SELECT`s only, opens **no** transaction, emits **no** DDL, and
**never imports `db/sync.py`**. `services/health.py` and the report route reach
`db/drift.py` and nothing else. `db/sync.py` may import `db/drift.py` (it needs the report
to know what to change); the dependency is one-way and a reversed import is a defect.

**Neither `db/drift.py` nor `db/sync.py` imports `app.db.schema`.** The registry arrives as
a **parameter**, exactly as `probe_health` already receives it and as
`routers/health.py` already passes it. This is what makes every step testable against a
purpose-built `MetaData` instead of against the real one.

**`require_role(Role.admin)` sits on the router, not the handlers**, so a route added later
cannot forget it (`backend-structure.md`; the pattern `005/003` DoD-4 set, and `006/005`
repeated). Every step that touches the router carries the DoD item asserting a route on
this router that declares no dependency of its own is still refused for a roleplayer.

**Routers versus services stays strict.** The router owns path, method, models,
dependencies and status code; it issues **no SQL**, holds **no rule**, and performs **no
registry lookup of its own** — it hands the whole registry down and lets `db/sync.py`
refuse an unknown table (D9). No handler translates a domain error by hand: the one
registered handler already covers every subclass.

**No DDL at startup, and this feature does not change that.** `main.py`'s lifespan stays
`yield` and nothing else. Feature `001` carries a DoD asserting `sqlite_master` holds no
application table after startup — **do not break it**. Every DDL statement in this feature
is emitted from inside an admin-authenticated request handler's service call and nowhere
else. `alembic` becomes a dependency without becoming a migration framework (D6).

**Transaction boundaries are the executor's own, because the connection dependency opens
none.** A Create is one transaction. A Sync's rebuild is one transaction that either
completes or leaves the table byte-for-byte as it was. The FK pragma dance around it is
D8's and is explicitly **outside** that transaction.

**This feature's wire carries no id.** The report is keyed on **table names**, so
`models/ids.py`'s two aliases are not used, there is no snowflake anywhere in the payload,
and the frontend row key is the table name. Stated because every other admin surface in the
project is id-addressed and a reader will look for the boundary rule that does not apply
here. The `{table_name}` path parameter is the one non-id path parameter in the admin
surface, and D9 says what constrains it.

**Mutations are never optimistic.** Every Create and every Sync is followed by a re-load of
the whole report (`ui-conventions.md`). That re-load is also how **US-018.AC-2** is
satisfied. Handler invocations are `void`-ed with a non-rethrowing catch.

**Failures render in place, so `notifyFailure` is called nowhere in this feature.** A page
failure is the inline `Alert` above the table. `002/006`'s scan — Mantine's notification
API imported by `shared/notifyFailure.ts` alone — stays true, and **no step touches
`frontend/tests/conventions.test.ts`**. **No success toast anywhere**: success is the
report refreshing and the row's status turning green.

**The admin area adds no stylesheet.** No `.css`, no `.module.css`, no style block under
`frontend/src/admin/`.

**Frontend is TypeScript only.** No `.js`, `.jsx`, `.mjs` or `.cjs`; `tsc --noEmit` is the
only static gate.

**The redaction rule** (`deployment.md`) binds every log line this feature adds: table
names, column names, status values, error codes — **never a row's contents, never a driver
message that could embed one**.

## Decisions — settled, with their reasoning

### D1 — What "differs" means: the compared set, and the deliberately uncompared set — the brief's first open question, closed

**User decision.** A table is compared on exactly three things:

| Compared | Detail |
|---|---|
| **the column set** | which declared column names are absent from the live table (**missing**), and which live column names the registry no longer declares (**extra**) |
| **each surviving column's declared SQLite type and its NOT NULL flag** | a column present on both sides whose normalised type text or nullability differs is a **changed** column, reported with its expected and its actual value |
| **the index set** | keyed on **(column list, uniqueness)**, not on index name — which declared indexes are absent (**missing**) and which live ones the registry no longer declares (**extra**) |

**Server defaults, `CHECK` constraint text and foreign-key clauses are deliberately NOT
compared.** SQLite stores each of them as raw SQL text that does not round-trip against a
SQLAlchemy declaration — the same constraint written by `create_all` and by a hand-edited
`ALTER` differs in whitespace, quoting and parenthesisation while meaning the same thing.
A false `drifted` row is worse than an unreported difference here, because the remedy it
invites is a **destructive rebuild that fixes nothing** and that the administrator will
then run again next week. Recorded as a deliberate gap, not an oversight.

This is the granularity the architecture already names — `data-model.md` and
`backend-structure.md` both cite `PRAGMA table_info` **and** `PRAGMA index_list` — and it
is the granularity that justifies Alembic batch operations at all: a retype or a column
drop is precisely what SQLite cannot do in place (D5).

Two normalisation rules follow, and both are the kind of thing that produces permanent
false drift if skipped:

- **The declared type is compiled through the SQLite dialect before comparison**, so
  `BigInteger().with_variant(Integer(), "sqlite")` yields `INTEGER` and the non-native
  `Enum` yields its `VARCHAR(n)` form — matching what `PRAGMA table_info` reports.
- **Both sides are upper-cased and whitespace-normalised** before they are compared, so
  `text` / `TEXT` and `VARCHAR(50)` / `VARCHAR (50)` are not differences.

**Indexes SQLite creates implicitly are not live indexes.** `PRAGMA index_list`'s `origin`
column distinguishes an explicitly created index (`c`) from one SQLite made for a `UNIQUE`
constraint (`u`) or a `PRIMARY KEY` (`pk`); only `c` rows count. Without this, `users`
— whose `username` is `unique=True` and which declares **no explicit `Index(...)` at all**
— would report an extra index forever, on a fresh, correct database.

### D2 — Three statuses, and `seed-missing` is declined explicitly

Per-table status is a closed three-value set: **in sync**, **missing**, **drifted**.
`admin-surfaces.md` records BookWriter's fourth value, `seed-missing`, as available prior
art and carries a `_TBD:` saying RPHelper has **no seed data in `docs/product/` at all**,
that there is therefore nothing for a Seed action to insert, and that inventing a use for
it "is not the architect's call". **It is not this plan's call either, and this plan
declines it in the same words.** No `seed-missing` status, no `Seed` action, no seed table,
no placeholder. The `_TBD:` is carried forward into `outcome.md`, not resolved.

The per-table report therefore carries: the table name, the status, the missing column
names, the extra column names, the changed columns (each with expected and actual type and
nullability), the missing indexes and the extra indexes. **And nothing else** — no row
count, no byte size, no timestamp (R5, and the cross-cutting constraint above).

### D3 — The walker covers `metadata.tables` only; views and virtual tables are a recorded gap

The registry walk iterates **`metadata.tables`** and nothing else. Views and
`vec0` / FTS5 virtual tables are **out of the report**.

The reason is that **none of them exists today**. `db/schema.py`'s docstring says the two
SQL views (`settled_entries`, `current_zone`) will live in that registry, and stage 004
adds the vector and FTS tables — but the registry declares `users` only, plus what `004`,
`005` and `006` add. **Do not invent a `kind` discriminator that has exactly one reachable
value**, and do not write a virtual-table comparison with no virtual table to compare: a
`vec0` table's `PRAGMA table_info` output does not resemble a `Table` declaration, and the
right comparison cannot be designed against zero examples.

`outcome.md` records that whichever feature introduces the views (`011` / `012`) and the
virtual tables (stage 004) **owns extending the report**, and that the `memos`
orphan-scope check `data-model.md` attributes to FEAT-005's drift report belongs to the
feature that creates `memos` (`015`).

### D4 — Create and Sync are defined by postcondition, which removes every "wrong state" error

Both actions are **idempotent and total** over the table's current state:

| Action | Postcondition | Missing table | Drifted table | In-sync table |
|---|---|---|---|---|
| **Create** | the table exists with the declared shape | creates it, with its declared indexes | **does nothing** | does nothing |
| **Sync** | the table matches the declared shape | creates it | rebuilds it (D5) | does nothing |

Two consequences worth stating, because both close off error codes a reader would expect:

- **Create never drops anything, in any state.** That is precisely the property that earns
  it a no-confirm (D7): its postcondition is always reachable without destroying data. A
  Create pressed against a row whose report has gone stale is a harmless no-op that answers
  with the current truth, not a failure.
- **Sync is a superset of Create.** It exists separately because UC-015 names "creating
  missing tables" as its own thing, because the UI offers them under different conditions,
  and because only one of the two can lose data.

So there is **no `table_already_exists` code, no `table_not_missing` code and no state
precondition on either route**. The only two failures are D9's.

### D5 — The rebuild is create-copy-drop-rename, via Alembic `batch_alter_table` in recreate mode

**User decision, in the user's own words: "Create a temporal table, move data, re-create
table, move data back."** That is the create-copy-drop-rename dance, and Alembic's
**batch operations in recreate mode** are the well-tested implementation of it. It is
adopted for that one capability and nothing else (`backend-structure.md`'s point 4).

The consequence, which is the whole of what the administrator is agreeing to:

- **Data in every column that survives the rebuild is preserved.** The copy carries across
  each column the registry still declares and the live table still has.
- **Only columns the registry no longer declares lose their data** — which is exactly the
  set the confirm names (D7).
- **A rebuild that cannot complete completes not at all.** A retype whose data will not
  cast, or a nullability tightening over existing NULLs, **fails** the rebuild; the
  transaction rolls back, the table is left byte-for-byte as it was, and the administrator
  gets `schema_apply_failed` (D9). Recorded deliberately in preference to a
  best-effort partial apply: a half-rebuilt table is a worse state than a drifted one, and
  a silent lossy cast is the failure mode this whole page exists to prevent.
- **No `_alembic_tmp_*` table survives a failure.** The temp table is created and dropped
  inside the same transaction as the copy.

### D6 — `alembic` becomes a runtime dependency, with four explicit negatives

`alembic` is named in the root `CLAUDE.md` stack table and throughout the architecture but
is **not currently a dependency**, and there is no `alembic.ini`, no `migrations/` and no
`env.py` anywhere in the tree. This feature adds it to `backend/pyproject.toml`'s runtime
`dependencies` with a compatible constraint. That is a deliberate `pyproject.toml` edit
inside step `003`'s scope, not creep.

`backend-structure.md` writes the four negatives out as explicit negatives *because* the
library normally implies all four, and this plan repeats them for the same reason:

1. **No `versions/` directory.**
2. **No revision chain.**
3. **No version table.**
4. **No automatic upgrade at startup** — `main.py`'s lifespan runs no DDL, and feature
   `001` has a DoD asserting `sqlite_master` holds no application table after startup.

What is used is `op.batch_alter_table` in recreate mode, driven from an
`alembic.migration.MigrationContext` / `alembic.operations.Operations` pair constructed
around the request's own `Connection`. Nothing else Alembic offers is imported.

### D7 — A lossy Sync warns and confirms, then proceeds; Create is not confirmed — the brief's second open question, closed

**User decision.** A Sync whose report lists **at least one extra column** — a column the
rebuild will drop — opens the shared `ConfirmModal`, **naming the columns that will be
dropped**, and applies on confirm.

**It does not refuse.** This page is the **only** path by which the schema ever changes and
there is no CLI alternative (`admin-surfaces.md` states both), so refusing would leave a
drifted table permanently drifted with no remedy anywhere in the product. A confirm is the
right instrument: it makes the loss visible to the one person who can judge it, without
making the loss impossible.

A Sync with **no** extra columns — a table that is only missing a column, or only differs
in a type, or is merely absent — applies **without a confirm**. The confirm is conditioned
on **data loss**, not on the action's name.

**`Create` is never confirmed**, in any state. Creating a missing table destroys nothing
and D4 guarantees it never can. This is the same distinction `005`'s D7 drew when it
recorded that re-enabling an account is not confirmed because it destroys nothing; it is
recorded here explicitly so the asymmetry between the page's two buttons reads as taken
rather than forgotten.

The confirm's consequence sentence names **the dropped column names and the table name**
and **nothing counted** (R5, and the cross-cutting constraint above). The confirm button
carries `color="red"`, matching `ConfirmModal`'s destroy convention.

### D8 — Foreign keys during a rebuild: off for the dance, checked before the commit, on afterwards

`db/engine.py`'s `connect` listener sets `PRAGMA foreign_keys = ON` on every connection.
A batch recreate **drops and renames tables**, so with foreign keys enforced the drop of a
table another table references fails, and the rename rewrites referencing clauses in ways
SQLite's own rebuild recipe explicitly warns about. It matters concretely already:
`006` declares `models.server_id` as `ON DELETE CASCADE` onto `llm_servers.id`.

So a Sync that rebuilds:

1. sets `PRAGMA foreign_keys = OFF` — **outside** any transaction, because SQLite silently
   ignores a change to this pragma inside one, which is the single easiest way to write
   this code so that it looks right and does nothing;
2. performs the whole rebuild inside **one** transaction;
3. runs `PRAGMA foreign_key_check` **before** that transaction commits, and treats any row
   it returns as a failure — rollback, `schema_apply_failed`;
4. restores `PRAGMA foreign_keys = ON` afterwards, **on both the success and the failure
   path**.

Step 4 is the one a reader will assume happens by itself. It does not: the connection is
pooled and the pragma is per-connection, so a Sync that left it off would silently disable
foreign keys for every later request served on that connection.

### D9 — Two new `DomainError` subclasses, and the route surface

`errors.py` today holds `SecretRefError` and `AlreadyConfiguredError`. The convention is a
subclass with `code` / `http_status` class attributes and nothing else — the one registered
handler already covers every subclass, and **no router ever translates an error by hand**.
`backend-structure.md`'s named-error table has no schema-remediation code at all, so both
of these are additions; `outcome.md` asks the architect to record them.

| `code` | Status | Raised when | `detail` carries |
|---|---|---|---|
| `unknown_table` | **404** | an apply route names a table the registry does not declare | the table name |
| `schema_apply_failed` | **500** | a Create or a Sync could not be applied — a driver error, a failed cast, a `foreign_key_check` violation | the table name and the operation (`create` or `sync`) |

Two decisions inside that table:

- **`schema_apply_failed` is 500, not 409 or 422.** Nothing about the request is malformed
  and nothing about the caller's authorization is wrong; the instance failed to do the
  thing it offered. That is the same posture `secret_ref_missing` already has.
- **The driver's message never reaches `detail`.** `detail` is structured and is the table
  name plus the operation. A SQLite error text can embed a column value (a failed `NOT
  NULL` or `CHECK`), which would put user content into an admin-facing payload and into the
  log line beside it. The message is not carried and not logged; the code, the table name
  and the operation are.

**The route surface.** Prefix **`/api/admin/database`**, mirroring `005`'s
`/api/admin/users` and `006`'s `/api/admin/llm-servers`.

| Method | Path | Does | Answers |
|---|---|---|---|
| `GET` | `/api/admin/database/tables` | the whole per-table report, registry declaration order, **no query parameters** | 200, the report model |
| `POST` | `/api/admin/database/tables/{table_name}/create` | D4's Create | 200, the freshly re-derived row for that table |
| `POST` | `/api/admin/database/tables/{table_name}/sync` | D4's Sync | 200, the freshly re-derived row for that table |

Notes that are decisions, not incidentals:

- **Each apply route answers with the table's report row re-derived *after* the apply**, so
  the route's own effect is assertable in one round trip and **US-018.AC-2** has a
  server-side witness as well as the page's re-load. The page still re-loads the whole
  report — the routes' answers do not make the never-optimistic rule optional.
- **`{table_name}` is validated by lookup in the registry, inside `db/sync.py`**, and the
  raw string is **never interpolated into SQL**. Only the registry's own `Table` object
  reaches the DDL. An unknown name is `unknown_table` 404 and is the *only* way a name
  the registry does not declare can be spelled — which is what makes the path parameter
  safe. The router does the lookup nowhere, so it holds no rule.
- **Two routes rather than one `apply`**, because the UI offers them under different
  conditions and only one of the two can lose data (D7). Their bodies are empty; neither
  takes a request model.
- **No route is keyed on anything but a table name**, no route takes a query parameter, and
  **no route returns a count of anything** (R5).

### D10 — `/api/health`'s `schema` roll-up is widened here, and the widening is a widening

`services/health.py`'s own docstring says feature `007` adds the `"drift"` branch and that
this is *"a widening of this function, not a rewrite of it"*. Today `probe_health` computes
`"ok" if declared <= present else "missing"` — a pure presence test with no `"drift"`
branch, even though `models/health.py`'s `SchemaState` already declares the value.

The widened mapping, with its precedence fixed here so no layer re-decides it:

| `schema` | When |
|---|---|
| `missing` | at least one declared table is absent — **unchanged from today's behaviour for the same input** |
| `drift` | every declared table is present and at least one differs (D1) |
| `ok` | otherwise |

`missing` outranks `drift` because a table that does not exist fails every query against
it, while a drifted one mostly works — and because the existing behaviour for a missing
table must not change.

Three things stay exactly as they are:

- **The existing `status` precedence** — `schema != "ok"` → `"degraded"`, elif not
  configured → `"unconfigured"`, else `"ok"`.
- **The registry arrives as a parameter**, never imported inside the service module;
  `routers/health.py` keeps passing it and is not edited.
- **`HealthProbeResult`'s field set, and the response shape.** The roll-up is one word and
  **names no table** — which is what keeps the endpoint safe unauthenticated
  (`backend-structure.md`).

**The cost, weighed.** The probe now runs the PRAGMA walk instead of one `sqlite_master`
read, on an endpoint that is also the container healthcheck target and is therefore called
on a timer. Over a registry of a handful of tables on a WAL SQLite file that is a
microsecond-scale read and it is worth it: `backend-structure.md` says the endpoint
"deliberately touches the database" because a health check that cannot fail tells an
operator nothing, and a coarse schema roll-up that cannot report drift is exactly that.
**Flip condition:** if the registry ever grows to a size where the walk shows up against
the healthcheck interval, the roll-up narrows back to presence and the drift branch moves
behind the admin route.

### D11 — The status badge colours, because no document specifies them

Neither `ui-conventions.md` nor `admin-surfaces.md` fixes a status-to-colour mapping
anywhere, and `admin-surfaces.md` asks for "a coloured status badge" without saying which
colours. This plan fixes them:

| Status | Badge colour |
|---|---|
| in sync | `green` |
| drifted | `yellow` |
| missing | `red` |

The ordering matches D10's severity precedence, so the page and the health roll-up cannot
disagree about which state is worse. `red` for missing because nothing works against a
table that is not there; `yellow` for drifted because the table works, just not as
declared, and the administrator is being asked to look rather than to panic.

**Colour is never the only signal.** The badge renders the **status word as text** and the
colour is redundant to it — `ui-conventions.md`'s accessibility floor, and the reason a
colour-only status column is a defect here. `outcome.md` asks the architect to record the
mapping so the next admin surface does not invent a second one.

### D12 — Six steps, following the briefing's suggested spine with one band re-cut

The briefing's spine is followed in shape. One change, on size rather than disagreement:
the briefing's band 1 (`db/drift.py` whole) plus band 2 (the health roll-up) is re-cut as
**`001` the two shape readers and the report value types** and **`002` the comparison, the
registry walk and the health roll-up**. Two reasons:

- the whole of `db/drift.py` in one step is comfortably over the 200-line budget once the
  value types, `PRAGMA table_info`, `PRAGMA index_list` / `index_info`, the declared-shape
  extraction and the comparison are all in it;
- the cut lands the **pure** half — a comparison over two shapes, with no database — in its
  own step, which is exactly the shape the pipeline's test-coder writes best against.

The briefing's band 2 (the health roll-up) is ~15 lines and does not stand alone; it joins
`002`, whose comparison it consumes. Bands 3, 4, 5 and 6 become steps `003`, `004`, `005`
and `006` unchanged.

Backend before frontend; every step independently verifiable; every step's Source and Test
file lists disjoint.

### D13 — MobX: no methods and no computed getters

`002`'s D2, confirmed by `003`'s D13, followed by every store in `003`–`006`, and
**stricter than `ui-conventions.md`'s sketch**, which shows computed getters. A MobX data
class holds **observable fields only**, constructed with
`makeAutoObservable(this, {}, { autoBind: true })`. Every derivation is a **pure free
function taking the data object**; every effect is a free function taking the object plus
an optional `AbortSignal`, which `runInAction`s its writes and **early-returns on
`signal.aborted` before writing**.

One store per page via `useState(() => new XPageState())`, **never `useMemo`**; the store
passed explicitly as a prop, no React context; `observer` on every component reading an
observable; **the confirm's open flag and its target row are component-local `useState`**.

`005`'s `outcome.md` already asks the architect to correct the doc's example; this feature
does not repeat the request.

## Vocabulary

| Term | Means here |
|---|---|
| **the registry** | the module-level `metadata` in `backend/app/db/schema.py`; always reached as a **parameter**, never imported by `db/drift.py` or `db/sync.py` |
| **declared shape** | a table's columns and indexes as the registry's `Table` object states them, compiled through the SQLite dialect |
| **live shape** | the same two things as `PRAGMA table_info` and `PRAGMA index_list` / `index_info` report them |
| **drift** | any difference between the two within D1's compared set |
| **the report** | the per-table records the whole feature is built around; one per `metadata.tables` entry, in declaration order |
| **status** | one of D2's three values — in sync, missing, drifted |
| **missing / extra / changed** | a column or index the live table lacks / has and the registry does not declare / has with a different type or nullability |
| **the rebuild** | D5's create-copy-drop-rename, run by Alembic's batch operations in recreate mode |
| **lossy** | a Sync whose report lists at least one **extra column**; the only condition that earns a confirm (D7) |

## Step map

| Step | Subject | Depends on |
|------|---------|------------|
| 001 | `db/drift.py` — the report value types and the two shape readers (live via PRAGMA, declared via the `Table` object) | — |
| 002 | `db/drift.py` — the pure comparison, the `metadata.tables` walk; `services/health.py`'s `"drift"` branch | 001 |
| 003 | `db/sync.py` — the batch-operation executor; the two error subclasses; `alembic` into the runtime dependencies | 001, 002 |
| 004 | `models/admin_db.py`, `routers/admin_db.py` behind router-level `require_role(Role.admin)`, one `include_router` line | 002, 003 |
| 005 | the page — store, report table, status badge, the `/database` route element | 004 |
| 006 | the per-row Create and Sync actions and the lossy-sync confirm | 005 |

## Test conventions inherited

**Backend** (`001`/`003`): tests live flat in `backend/tests/` as `test_<module>.py`, with
functions named **`test_<behaviour>__DoD<n>`**, each docstring citing the DoD clause and
its step file. `conftest.py` provides the autouse `isolated_settings_environment` (clears
every `RPHELPER_*` variable and the settings cache), `db_settings` (a real `.sqlite`
**file** under `tmp_path`, **never `:memory:`**) and `db_engine`. **Mocks are never used
for SQL behaviour** — a rebuild is tested against a real file, because the whole point of
the batch dance is what SQLite actually does. **There is no shared app or client fixture**:
each router test module builds its own `TestClient(create_app())` **locally and not as a
context manager** (the lifespan is deliberately bypassed) and overrides settings through
`app.dependency_overrides[get_settings]`, never by mutating a global.

`db/drift.py` is covered by **two** test modules, `test_drift_introspection.py` and
`test_drift_report.py`, because two steps write it. That is the same one departure from
one-file-per-module `006` made for `llm_registry.py`, and it is deliberate. Steps `002`
and `003` also extend two **existing** test modules — `test_health.py` and
`test_errors.py` — which is why those files appear in a step's Test files list.

**Frontend** (`002`–`006`): Vitest configured inside `frontend/vite.config.ts`'s `test`
block — a separate `vitest.config.*` is forbidden. `environment: "jsdom"`,
**`globals: false`**, so `describe` / `it` / `expect` are explicit imports from `"vitest"`.
Tests live under `frontend/tests/admin/` mirroring `src/`, named `*.test.ts` /
`*.test.tsx`, each `it` title ending **`— DoD-N`**. `@testing-library/react`,
`/jest-dom` and `/user-event` are available; **`fetch` is stubbed per test with no
network-mocking library**. A component test rendering Mantine wraps in
`shared/AppProviders`. Tests assert **rendered behaviour**, never internal structure.
`npm test` is `vitest run`.
