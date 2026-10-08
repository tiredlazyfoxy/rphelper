# Feature 007 — Schema drift and remediation · intended documentation changes

Written by the planner before implementation; applied by `/architect` at finalization.
Grouped by target file. The coder appends `## Observations` at the bottom.

---

## `docs/architecture/backend-structure.md`

### A1 — Two new rows in the named-error table

- **Section:** "The error model" → the named-errors table.
- **Change:** add two rows, both introduced by FEAT-005:

| `code` | Raised when | `detail` carries | Realizes |
|---|---|---|---|
| `unknown_table` | A drift-page apply route names a table the registry does not declare | the table name | FEAT-005, UC-015 |
| `schema_apply_failed` | A `Create` or a `Sync` could not be applied — a driver error, a failed cast, or a `PRAGMA foreign_key_check` violation | the table name and the operation (`create` \| `sync`) | FEAT-005, UC-015 |

  with statuses **404** and **500** respectively. Record the two decisions inside them:
  **500 rather than 409 or 422**, because nothing about the request is malformed and the
  instance failed to do what it offered — the same posture `secret_ref_missing` already
  has; and **the driver's message never reaches `detail` or a log line**, because a SQLite
  error text can embed a column *value*, which would put user content into an
  administrator-facing payload (R5, `deployment.md`'s redaction rule).
- **Reason:** the table has no schema-remediation code at all today, and the brief's
  fifth scope-in item — "the administrator-facing result of a failed apply" — has no
  vocabulary without one.

### A2 — The admin database route surface, and where the table name is made safe

- **Section:** Layout (the `db/drift.py`, `db/sync.py` and `routers/admin_db.py` lines) and
  "Authorization as router dependencies".
- **Change:** record the chosen prefix **`/api/admin/database`** and its three routes —
  `GET /tables` (the whole report), `POST /tables/{table_name}/create`,
  `POST /tables/{table_name}/sync`, all answering 200 and all taking **no body and no
  query parameter**. Record four decisions embedded in it: each apply route **answers with
  the per-table report re-derived after the apply**, giving US-018.AC-2 a server-side
  witness beside the page's re-load; **`{table_name}` is validated by lookup in the
  registry inside `db/sync.py`, never in the router**, and the raw string is never
  interpolated into SQL — only the registry's own `Table` object reaches the DDL, which is
  what makes a non-id path parameter safe here; **two routes rather than one `apply`**,
  because the UI offers them under different conditions and only one of the two can lose
  data; and `require_role(Role.admin)` attached **once at router level**, making
  `admin_db.py` the third and last of the three `admin_*.py` routers the section
  anticipates. Record also that this is the **one admin route family not keyed on a
  snowflake** — its wire carries no id at all — so the JSON id boundary has no call site
  here.
- **Reason:** no document fixed the paths, and FEAT-001..004's plans set the precedent of
  recording a chosen route surface rather than leaving it to be discovered. The
  table-name-safety rule in particular is invisible from the route table and is the one
  thing a later contributor could undo by "simplifying" the lookup into the handler.

### A3 — `db/sync.py` resolves the table itself, which is a small correction to the doc

- **Section:** "Schema evolution — the registry is the truth, the administrator applies",
  the "Where the executor lives: `db/sync.py`" paragraph.
- **Change:** the section says the executor "takes a drift-report row plus the registry's
  `Table` object". As built it takes the **registry and a table name**, resolves the
  `Table` itself, raises `unknown_table` when the registry does not declare it, and calls
  `db/drift.py` for the report row it needs. Record the reason: with the doc's signature
  someone has to perform the lookup, and the only caller is a router — which would put a
  rule and a refusal in the layer that is supposed to hold neither. Record that
  `db/sync.py` may import `db/drift.py` and that the reverse import is a defect, so the
  section's own "the code path that only reports cannot write" reads as the one-way
  dependency it is.
- **Reason:** the two sentences are one signature apart and a skeleton agent binding to the
  doc's version would produce a router that holds a rule.

### A4 — `alembic` is now a real dependency, and the four negatives are now testable

- **Section:** "Schema evolution", point 4, cross-referenced with the Layout block.
- **Change:** record that FEAT-005's plan moved `alembic` into `backend/pyproject.toml`'s
  **runtime `dependencies`** — it was named in the stack table and in this section but was
  not a dependency at all — and that the four explicit negatives are now assertions a
  verifier checks rather than intentions: **no `versions/` directory, no revision chain,
  no version table, no automatic upgrade at startup**, with `main.py`'s lifespan still
  running no DDL and FEAT-001's `sqlite_master`-is-empty-after-startup assertion still
  passing. Record the narrow API surface actually used —
  `alembic.migration.MigrationContext` plus `alembic.operations.Operations` around the
  request's own `Connection`, and `batch_alter_table` in recreate mode — and that nothing
  from `alembic.config`, `ScriptDirectory`, `EnvironmentContext` or `command.*` is
  imported.
- **Reason:** the section writes the negatives out precisely because "we use Alembic"
  without them is how a `versions/` directory arrives later; now that the dependency is
  real, the negatives should be recorded as enforced rather than as hoped.

### A5 — The foreign-key posture of a rebuild

- **Section:** "Schema evolution" (the batch-operations paragraph) and "Database access"
  (the per-connection PRAGMA list).
- **Change:** record that a batch recreate drops and renames tables, so a Sync sets
  `PRAGMA foreign_keys = OFF` **outside** the transaction, performs the rebuild inside one
  transaction, runs `PRAGMA foreign_key_check` **before** committing and treats any
  returned row as a failure, and restores `PRAGMA foreign_keys = ON` afterwards on **both**
  the success and the failure path. Record the two reasons a reader will not infer:
  SQLite **silently ignores** a change to that pragma inside a transaction, so the obvious
  ordering compiles and does nothing; and the connection is **pooled**, so a Sync that left
  the pragma off would disable foreign keys for every later request on that connection.
- **Reason:** `db/engine.py` sets `foreign_keys = ON` on every connection and the Database
  access section presents it as an invariant. This is the one code path that must suspend
  it, and an unrecorded suspension is the kind of thing a later reader deletes.

### A6 — `/api/health`'s `schema` roll-up, as widened

- **Section:** `/api/health`.
- **Change:** record the mapping and the precedence now that the `"drift"` branch exists:
  **`missing`** when a declared table is absent, **`drift`** when every declared table is
  present and at least one differs, **`ok`** otherwise — with **missing outranking drift**
  because a table that does not exist fails every query against it. Record that the
  `status` precedence is unchanged, that the registry still reaches `probe_health` as a
  **parameter**, and that the roll-up is **one word naming no table**, which is what keeps
  the endpoint safe unauthenticated. Record the cost and its flip condition: the probe now
  runs the PRAGMA walk instead of one `sqlite_master` read on an endpoint that is also the
  container healthcheck target; accepted over a handful of tables on a WAL file, and if
  the registry grows to where the walk shows against the healthcheck interval, the roll-up
  narrows back to presence and the drift branch moves behind the admin route. Record that
  caching the probe is explicitly rejected, since a health check that cannot fail is what
  this section says the endpoint exists not to be.
- **Reason:** the section documents the three-value `schema` field but nothing has ever
  produced `"drift"`; the precedence between two non-`ok` values is new information that
  two layers now depend on.

---

## `docs/architecture/admin-surfaces.md`

### B1 — The report's three statuses, and `seed-missing` declined in the doc's own words

- **Section:** "Database page — FEAT-005 + FEAT-018's admin half", the scope-discipline
  paragraph and the `_TBD:` on Seed.
- **Change:** record that FEAT-005's plan **declines** the fourth status and the `Seed`
  action, for the reason the `_TBD:` itself gives — there is no seed data in
  `docs/product/` at all, so there is nothing for the action to insert, and inventing a
  use for it is not the plan's call either. The status set is therefore fixed at **three
  values: in sync, missing, drifted**, declared once in `db/drift.py` and reused by the
  router model and the frontend row type. Keep the `_TBD:` as a `_TBD:` rather than
  resolving it; record only that the plan looked and declined.
- **Reason:** the `_TBD:` hands the question to FEAT-005's plan; the plan answered "no" and
  that answer should be visible in the doc, or the next planner re-opens it.

### B2 — What the report compares, and what it deliberately does not

- **Section:** "Database page", the per-table drift report paragraph.
- **Change:** record the granularity (**user decision**, plan `context.md` D1): a table is
  compared on its **column set**, each surviving column's **declared SQLite type** and
  **NOT NULL** flag, and its **index set keyed on (column list, uniqueness) rather than on
  index name**. Record that **server defaults, `CHECK` constraint text and foreign-key
  clauses are deliberately NOT compared**, because SQLite stores them as raw SQL text that
  does not round-trip against a SQLAlchemy declaration, and a false `drifted` row invites a
  destructive rebuild that fixes nothing. Record the two normalisations without which the
  correct database reports drift forever: the declared type is compiled **through the
  SQLite dialect** (so a `BigInteger().with_variant(Integer(), "sqlite")` matches a live
  `INTEGER`), and indexes SQLite creates implicitly for a `UNIQUE` constraint or a
  `PRIMARY KEY` are **not** live indexes. Record the per-table report's fields and that it
  carries **no row count, no byte size and no timestamp**.
- **Reason:** the section says "a summary of missing and extra columns" and cites the two
  pragmas, but the granularity *is* the administrator's whole signal — `brief.md` says so —
  and an unrecorded granularity is re-decided by the next person to touch the module.

### B3 — Create and Sync, defined by postcondition

- **Section:** "Database page", the paragraph authorizing `Sync`.
- **Change:** record that both actions are **idempotent and total** over a table's current
  state (plan `context.md` D4): **Create** guarantees the table exists with the declared
  shape and **never drops anything in any state**, doing nothing when the table already
  exists; **Sync** guarantees the table matches the declared shape, creating it when
  absent, rebuilding it when drifted, doing nothing when in sync. Record the consequence
  that there is therefore **no state precondition and no "wrong state" error code** on
  either route, and that Sync is a superset of Create which exists separately because
  UC-015 names creating missing tables as its own thing and because **only one of the two
  can lose data**. Record that the page **offers each action only in the state it applies
  to, absent rather than disabled**, and that an **in-sync row renders no action trigger at
  all** rather than a menu of no-ops.
- **Reason:** the doc authorizes both actions without saying what either does in the states
  it was not designed for, which is exactly where a plan invents an error code.

### B4 — The rebuild mechanism and what it preserves

- **Section:** "Database page", the `db/sync.py` sentence, cross-referenced with
  `data-model.md`'s "Schema drift and rebuild".
- **Change:** record the execution shape the user fixed in their own words — *"create a
  temporal table, move data, re-create table, move data back"*, i.e. Alembic's
  `batch_alter_table` in **recreate mode** — and its consequence, which is what the
  confirm is about: **data in every column that survives the rebuild is preserved**, and
  only columns the registry no longer declares lose theirs. Record that a rebuild that
  cannot complete completes not at all: a cast that fails or a nullability tightening over
  existing NULLs rolls the transaction back, leaves the table byte-for-byte as it was and
  raises `schema_apply_failed`, with no `_alembic_tmp_*` table surviving — a best-effort
  partial apply is rejected because a half-rebuilt table is a worse state than a drifted
  one.
- **Reason:** the doc names Alembic batch operations as the executor but not what the
  administrator is actually agreeing to when they press the button, which is the only fact
  the confirm can honestly carry.

### B5 — The status badge's colours

- **Section:** "Database page", the "coloured status badge" phrase.
- **Change:** fix the mapping, which **no document specifies today** — neither this file
  nor `ui-conventions.md`: **in sync → `green`, drifted → `yellow`, missing → `red`**.
  Record the reason for the ordering: it matches `/api/health`'s severity precedence
  (A6), so the page and the roll-up cannot disagree about which state is worse; `red`
  because nothing works against a table that is not there, `yellow` because a drifted table
  works, just not as declared. Record that **the badge renders the status word as text and
  colour is redundant to it** — a colour-only status column fails `ui-conventions.md`'s
  accessibility floor — and that the mapping is derived by one pure helper so the component
  maps nothing.
- **Reason:** it is a genuine gap: "a coloured status badge" with no colours named means
  the next admin surface invents a second mapping.

### B6 — Two recorded gaps in the report: views and virtual tables

- **Section:** "Database page", the per-table report paragraph, as an explicit note.
- **Change:** record that FEAT-005's report walks **`metadata.tables` only**, so the two
  SQL views (`settled_entries`, `current_zone`) and the `vec0` / FTS5 virtual tables are
  **out of it**, and that this is a known gap rather than an oversight: **none of them
  exists yet** — the registry declares `users` plus what FEAT-002/003/004's features add —
  and a `kind` discriminator with exactly one reachable value, or a virtual-table
  comparison designed against zero examples, is worse than the gap. Record the ownership:
  whichever feature introduces the views (FEAT-009/FEAT-010's plans, `011`/`012`) and
  whichever introduces the vector and FTS tables (stage 004) **owns extending the report**,
  and each should add the case with its first real instance.
- **Reason:** a drift report that silently ignores half the schema is a correctness claim
  it does not hold; recording the boundary and its owner turns it from a bug into a
  scheduled extension.

### B7 — The page ships with the report and its row actions only

- **Section:** "Database page", the page-level actions table.
- **Change:** record that as delivered the page carries **the report table and its per-row
  Create and Sync and nothing else**. **Rebuild index (UC-016 / US-019) is deferred to
  `fast/002.vector-index-rebuild`**, which has no vectors to rebuild until stage 004
  creates the `vec0` tables; **Export** and **Import** belong to features `030` and `031`.
  Record that no disabled placeholder is built for any of the three. Note that
  FEAT-004's plan `context.md` carries a **stale** cross-reference calling UC-016 "feature
  `007`'s"; `007`'s `brief.md` supersedes it.
- **Reason:** the table presents all three page-level actions as part of this page, and a
  reader of the doc against the shipped page would otherwise read three absences as three
  defects.

---

## `docs/architecture/data-model.md`

### C1 — The orphan-scope check belongs to the feature that creates `memos`

- **Section:** `memos`, the polymorphic-scope trade paragraph.
- **Change:** the paragraph's mitigation says "FEAT-005's drift report includes an
  orphan-scope check". Record that FEAT-005's feature **does not build it**, because
  `memos` does not exist until FEAT-012's feature (`015`) and there is nothing to check;
  and record that the check is a **content** check over `(scope, scope_id)` rather than a
  structural one, so it does not belong in the structural per-table report this feature
  built at all. Name its owner: the feature that creates `memos`, as its own admin-facing
  check or as a widening of the Database page, whichever that plan chooses.
- **Reason:** the sentence attributes work to a feature that has now shipped without it;
  left as-is it reads as a delivered guarantee.

### C2 — "Schema drift and rebuild", as built

- **Section:** "Schema drift and rebuild".
- **Change:** record the three-value status set (B1), the compared and deliberately
  uncompared set (B2), the `metadata.tables`-only walk and its recorded gap (B6), and that
  the structure/content split the section already states held: **this feature built the
  structural half only**, and UC-016's rebuild is `fast/002`'s. Record that `db/schema.py`
  was **not edited by this feature** — the registry gained no table and no column — which
  is the practical form of "the registry stays the truth".
- **Reason:** the section is the schema-level statement of what FEAT-005 needs; recording
  what was actually built against it keeps the next reader from assuming the rebuild half
  shipped too.

---

## `docs/architecture/ui-conventions.md`

### D1 — The confirm table gains a conditional row, and loses one

- **Section:** "NEW — the confirm convention", the table of confirmed actions.
- **Change:** add **A lossy `Sync` on the drift page** (FEAT-005) with its consequence —
  the rebuild drops the columns the registry no longer declares and their data goes with
  them, while every surviving column's data is preserved. Record that it is
  **conditional**: the confirm fires only when the row lists **at least one extra column**,
  and a Sync with nothing to drop applies directly — the confirm is conditioned on **data
  loss**, not on the action's name. Record explicitly that **`Create` is never confirmed**,
  in any state, because it is provably incapable of dropping anything (B3) — the same
  shape FEAT-003's plan used when it recorded that re-enabling an account is not confirmed
  because it destroys nothing. Record also that the section's existing **Rebuild the vector
  index** row is **not yet realized**, since UC-016 is deferred to
  `fast/002.vector-index-rebuild`.
- **Reason:** the section invites FEAT-005's planner to revisit the set and this is the
  revision; a conditional confirm and a deliberate non-confirm that appear only in a plan
  will both drift.

### D2 — The confirm may name structure; it may never name content

- **Section:** the confirm convention's "must not name a blast radius" paragraph.
- **Change:** record the distinction FEAT-005 had to draw, because the drift page is the
  first surface where a confirm legitimately names *something*: **a table name, a column
  name, an index's column list and a SQLite type are administrative data** — identical on
  every instance, declared in `db/schema.py`, and UC-014 is unanswerable without them — so
  the lossy-Sync confirm names the columns it will drop. **A row count is content** and
  stays forbidden, in the confirm, in the report, in an apply response and in a log line.
  Record the forbidden strings alongside the existing "Are you sure? N sessions use this
  model": **"N rows will be lost"**, **"N rows will be rebuilt"**, **"rows affected"**.
- **Reason:** the paragraph currently reads as "a confirm names nothing specific", which
  would have made the only informative sentence available here impossible; the line is
  between structure and content, not between specific and vague.

---

## `docs/architecture/quick-reference.md`

### E1 — Index the new surfaces

- **Change:** add `unknown_table` (404) and `schema_apply_failed` (500) to the error-code
  list; add the `/api/admin/database` route surface and its three routes; record that
  `/api/health`'s `schema` can now actually be `"drift"` and note the
  missing-outranks-drift precedence; add the three-value drift status set and the badge
  colour mapping; record `alembic` as a **runtime** dependency with its four negatives;
  and record that `docs/plans/fast/002.vector-index-rebuild` owns UC-016 / US-019.
- **Reason:** the file is the dense agent-first index and these are exactly the facts an
  agent looks up there rather than reading four long docs.

---

## Notes for the architect, not doc changes

- **Six steps, following the briefing's spine with one band re-cut.** `db/drift.py` is
  built over two steps rather than one — the value types and the two shape readers, then
  the pure comparison, the registry walk and the health roll-up — on size, and because the
  cut lands the pure half in its own step. The briefing's separate health-roll-up band is
  ~15 lines and joined the step whose comparison it consumes. Reasoning is in plan
  `context.md` D12.
- **Two test modules cover one source module.** `db/drift.py` is covered by
  `test_drift_introspection.py` and `test_drift_report.py` because two steps write it —
  the same deliberate departure from one-file-per-module FEAT-004's plan made for
  `llm_registry.py`.
- **A stale cross-reference the architect may want to chase:** plan
  `docs/plans/006.llm-server-connections/context.md` calls UC-016 "feature `007`'s". It is
  not; `007`'s `brief.md` defers it to `fast/002`. Plans are not the architect's to edit,
  but `quick-reference.md`'s ownership line (E1) is the durable correction.
- **`_TBD:` carried, not resolved:** `admin-surfaces.md`'s Seed / `seed-missing` `_TBD:`
  (B1 — looked at and declined), and `ui-conventions.md`'s no-pagination `_TBD:` — a drift
  report has one row per registry table and is the smallest list in the product, so that
  doc's flip condition is unchanged.
- **One thing worth a second look:** `schema_apply_failed`'s **500**. It is the honest
  status for "the instance failed to do what it offered", but it means a routine
  administrator action can produce a 500 in the logs, exactly as FEAT-004's plan flagged
  for `secret_ref_missing`. The two are now siblings and the architect may want to decide
  their posture together rather than one at a time.
- **`docs/product/` gap worth noting, not closing here:** no acceptance criterion says
  whether a remediation that would lose data should refuse or warn — `brief.md` records it
  as an open question and the **user decided** it (warn and confirm, plan `context.md` D7).
  Recorded as a design decision under `ui-conventions.md`'s explicit invitation, not as a
  discovered requirement.

---
Status: Applied 2026-10-01 — /architect finalization (with /product-spec finalization the same day)
Applied items: 18 (A1–A6, B1–B7, C1–C2, D1–D2, E1; A1, B4, B6 and D1 with modification)
Rejected items: 0
Notes: A1 — the "same posture as `secret_ref_missing`" sentence was held (H1) and is now written as the user-decided shared 500 posture in `backend-structure.md`'s error model. D1 cites US-018.AC-3..AC-5 — the lossy-Sync confirm is now a product requirement, which closes the Notes' `docs/product/` gap line. B6 additionally records (status.md, step 003) that once views exist a Sync of a view-referenced table may fail safely at the rename until the views feature handles it. B4 additionally records the post-copy cast probe (INTEGER/REAL/NUMERIC/DECIMAL/BOOLEAN targets only). A6 was largely present from batch 1 (precedence); the cost, flip condition and caching rejection were added.
