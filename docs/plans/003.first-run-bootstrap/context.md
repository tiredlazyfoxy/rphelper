# Feature 003 — First-run bootstrap · feature-wide context

## What this feature is

Turns an unconfigured instance into a usable one: the `bootstrap` entry detects that no
database and no administrator exist, offers to create a database with a first
administrator, creates both in one operation, and refuses to act at all once the
instance is configured. The agreed boundary is `brief.md` in this folder — its
Definition and its Scope In/Out lists bound every step here and are **not** restated or
widened. Read it first.

## Product ids

`FEAT-001`, via **UC-001**, **UC-003**, **US-001**, **US-003**.

| Criterion | Where it lands |
|---|---|
| US-001.AC-1 | steps `002`, `003` (backend), `005` (the operator's action) |
| US-001.AC-2 | **not delivered here** — deferred to `004.authentication-session`, see D9 |
| US-003.AC-1 | steps `002`, `003` (the guard), `004` (the refusal is offered nowhere) |
| US-003.AC-2 | step `004` (the refusal directs to sign in) |

**UC-002 / US-002 — bringing an instance up from an export — is out**, per `brief.md`.
It belongs to `fast/003.bootstrap-from-export`, which the roadmap sequences after
`031.import-and-id-remapping`. Two obligations follow and are held by steps `003` and
`004`: the bootstrap surface must leave **room** for a second option without building
it, and `require_unconfigured` must already be the thing that will guard it (D6).

A `[test]` Definition-of-done item cites the `US-###.AC-#` it verifies wherever one
applies. Items that are structural or architectural obligations rather than product
criteria stand on their own, as they do in `001` and `002`.

## Assumption every step rests on — 001 and 002 are planned, not built

`backend/` and `frontend/` **do not exist yet**. Features `001.backend-foundation` and
`002.frontend-foundation` are planned with every step `pending`, and the roadmap build
order is `001 → 002 → fast/001 → 003`. Therefore:

- **No step here quotes an exact signature for anything `001` or `002` delivers.** Their
  `## Skeleton` records do not exist, so there is nothing frozen to bind to. Borrowed
  interfaces are named by **role and module path** in prose — "the connection dependency
  from `app/db/engine.py`", "the settings accessor in `app/config.py`", "the request
  function in `frontend/src/shared/api.ts`" — and the **skeleton agent resolves the
  exact names against the delivered code**.
- The citation for every borrowed interface is the step file that delivers it:
  `docs/plans/001.backend-foundation/00{1,3,4,5,6}.*.md` and
  `docs/plans/002.frontend-foundation/00{4,5,6}.*.md`. Where a step needs a narrow fact
  from one of those, its `<SSS>.context.md` names the file and section rather than
  restating it.
- If the delivered `001`/`002` code contradicts what a step file assumes about it, that
  is a **skeleton hand-back**, not something a coder improvises around.

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

- `docs/architecture/backend-structure.md` — Layout, "Authorization as router
  dependencies", the error model, `/api/health`, Configuration, the JSON id boundary,
  routers versus services, Persistence access (Core, explicit `begin()`).
- `docs/architecture/data-model.md` — `users` (the column list is authoritative),
  Identifiers, and `auth_sessions` **for the boundary only, not to build**.
- `docs/architecture/frontend-structure.md` — per-entry responsibilities, why the
  `bootstrap` entry is separate, navigation between entries, the MobX convention, the
  API client, ids-are-strings, the two stylesheets.
- `docs/architecture/domain-rules.md` — "Roles — the ladder every rule below assumes".
- `docs/architecture/deployment.md` — the `supervisord`/502/not-ready-yet passage, the
  nginx `/bootstrap/` fallback, and the compose healthcheck (see D5).
- `docs/product/use-cases/FEAT-001.*.md`, `docs/product/stories/FEAT-001.*.md`.

Cited, never copied. Where a step needs a declaration the architecture gives verbatim
(the `users` column list, the wire shape of a domain error, the two snowflake aliases),
the step context points at the section and the skeleton agent reproduces it.

## Files this feature touches

```
backend/
  pyproject.toml                  # + argon2-cffi                              (001)
  app/
    roles.py                      # NEW — the two-value Role enum              (001)
    errors.py                     # + already_configured                       (002)
    db/schema.py                  # + the users Table literal                  (001)
    db/engine.py                  # transactional DDL on every connection      (002)
    services/passwords.py         # NEW — the hashing seam                     (001)
    services/bootstrap.py         # NEW — the configured fact + the creation   (002)
    services/health.py            # delegates its configured branch            (002)
    models/bootstrap.py           # NEW — request/response models              (003)
    routers/bootstrap.py          # NEW — the route + require_unconfigured     (003)
    main.py                       # + include the bootstrap router             (003)
frontend/
  src/
    shared/notReady.ts            # NEW — the not-ready-yet classification     (004)
    bootstrap/main.tsx            # placeholder route table replaced           (004)
    bootstrap/BootstrapPage.tsx   # NEW — the three states                     (004, 005)
    bootstrap/bootstrapState.ts   # NEW — the entry's store + free functions   (004)
    bootstrap/createAdminDraft.ts # NEW — the draft + validators + submit      (005)
    bootstrap/CreateAdminForm.tsx # NEW — the form                            (005)
```

**`frontend/src/bootstrap/index.html` is not touched.** `002`'s step `006` already
creates it as a document with lang, charset, viewport, a title, one mount element and a
module script pointing at the sibling `main.tsx`; nothing this feature does changes any
of that, so it appears in no step's Source files.

**Out of scope, and a step that creates one is out of scope:** `auth_sessions`, any
session token or cookie, `ROLE_LADDER`, `require_role`, `require_user`, `/api/me`,
`db/drift.py`, `db/sync.py`, `alembic.ini`, any `versions/` directory, any DDL at
startup, an admin-seed setting, an import route or an import UI, a password-reset or
rehash-on-verify path, any second stylesheet import in the `bootstrap` entry.

## Cross-cutting constraints every step holds

**Routers versus services stays strict.** The router owns path, method, models, the
router-level dependency, the status code and nothing else; it issues **no SQL** and
holds no rule. The service takes plain arguments, returns plain results or raises a
typed error, and **never imports `fastapi`, never sees a `Request`, never knows a status
code**. Direction is one-way: `routers → services → db`.

**Transaction boundaries are the service's own `with conn.begin():` blocks.** The
connection dependency from `001` opens no transaction. Creating the schema and inserting
the first administrator is **one** such block (D8) — a half-bootstrapped instance must
not be reachable.

**No DDL at startup.** `main.py`'s lifespan still runs no schema creation, no upgrade
and no schema check. Creating the schema here is a **request-time operation the operator
triggers**, not startup remediation and not `007`'s admin-triggered drift sync.

**The JSON id boundary.** The new administrator's `id` crosses the wire as a decimal
string. Every id-typed field on a pydantic model uses one of `001`'s two annotated
aliases from `app/models/ids.py`; a bare `int` id field is the defect. On the frontend
an id is a `string` end to end — and the `bootstrap` entry reads no id at all except the
one the create response returns, which it does not parse.

**The redaction rule** (`deployment.md`) binds every log line: ids as decimal strings,
error codes, counts, statuses — never a username's password, never a hash, never a
resolved secret. `services/passwords.py` logs nothing.

**The `bootstrap` entry stays pre-database.** No session, no user, **no API surface
beyond `GET /api/health` and the bootstrap routes** (`frontend-structure.md`). It must
not acquire an `/api/me` call or any authenticated store. It imports no stylesheet
directly — `global.css` reaches it transitively through `shared/AppProviders`, and
`shell.css` remains `src/app/main.tsx`'s alone.

**Backend is fully type-annotated; the frontend is TypeScript only.** No `.js`, `.jsx`,
`.mjs` or `.cjs` file is authored anywhere under `frontend/`, and there is no linter —
`tsc --noEmit` is the only static gate.

## Decisions — settled, with their reasoning

### D1 — Password hashing: Argon2id via `argon2-cffi`, behind `services/passwords.py`

`brief.md`'s second open question, closed by user decision. `003` adds `argon2-cffi` to
`backend/pyproject.toml` and puts hashing behind **one tiny module** exposing a hash
operation and a verification operation, so the algorithm is swappable in one file and
`004`'s login verifies through the same seam.

**The parameters are the library's own current defaults, not hand-picked numbers.**
`argon2-cffi` owns them and tracks the maintained baseline; a plan that invented
`time_cost`/`memory_cost`/`parallelism` literals would be pinning a guess and would go
stale silently.

The stored value is the library's **self-describing encoded string**
(`$argon2id$v=19$m=...`), so the parameters live inside the hash. A later parameter
change is therefore a rehash-on-verify concern, **not** a schema change — and **`003`
does not build rehash-on-verify**; it has exactly one hash to write and no login path
to rehash from.

### D2 — `already_configured` is `409 Conflict`, and carries no `detail`

`backend-structure.md` fixes the code, the "raised when" and that `detail` carries
nothing; it does **not** fix the status, so the plan chooses. **409 Conflict**: the
request is well formed and the caller is not being authenticated or authorized — it is
refused because the instance's current state conflicts with the operation. 403 was
rejected because nothing about the caller's identity is being judged (there are no
identities yet), and 404 was rejected because hiding the route would make UC-003's
"directs them to sign in instead" undiagnosable. `outcome.md` asks the architect to
record it in the error table.

### D3 — `configured` is read from the `users` table **and** its contents

`brief.md`'s first open question, and it is already answered by
`001/006.app-factory-and-health.md:44-59` and `backend-structure.md:629-631`:

> a `users` table present **and** holding at least one row whose role is administrator.

Neither of the other two candidates works, and this is the load-bearing answer to
UC-003, which must refuse **in every case an administrator already exists**:

- **Not the database file's presence.** SQLite creates the file on mere connection
  (`001/005` DoD-5), so the file proves nothing — a health probe alone would create it.
- **Not the `users` table alone.** An empty `users` table means no administrator exists,
  so bootstrap must still be offered; refusing there would brick an instance whose
  tables were created but never populated.

### D4 — The fact has exactly one definition, in `services/bootstrap.py`

`services/health.py` (from `001`) and `require_unconfigured` (from `003`) must agree
forever, because `/api/health`'s `configured` is what the UI offers bootstrap on and
`require_unconfigured` is the server-side enforcement of *the same fact*
(`backend-structure.md:629-631`). So the predicate lives in `services/bootstrap.py` and
**`services/health.py` delegates to it** — that is the widening `001/006:52` promised
("Feature `003` sharpens the same branch; it must not have to rewrite it"), performed as
a delegation rather than a second copy of the query.

### D5 — The health status roll-up is **not** re-decided, and a pre-bootstrap instance reports `degraded`

`001/006` fixes the precedence: a `schema` other than `"ok"` gives `"degraded"`;
otherwise `configured` false gives `"unconfigured"`; otherwise `"ok"`. Once `users` is
in the registry (step `001`), a pre-bootstrap database has a **missing** registry table,
so a fresh instance reports `status: "degraded"`, `configured: false`,
`schema: "missing"`.

That is left exactly as `001` decided it, for two reasons: the precedence is a criterion
`001` already ships and verified, and the report is honest — a declared table really is
absent. The consequence that matters is a **frontend** one and is held by step `004`:
**the `bootstrap` entry branches on `configured` alone and never on `status`**, which is
what `backend-structure.md` designates as FEAT-001's signal anyway. `status:
"unconfigured"` remains reachable for a database whose tables exist with no
administrator row in them. `outcome.md` asks the architect to record the pre-bootstrap
triple so nobody reads `"degraded"` as a fault.

**The container healthcheck survives this, and why it survives is load-bearing.**
`deployment.md:130-131` defines the compose healthcheck as `curl -f` against
`/api/health`. `curl -f` fails on an HTTP **error status**, and `/api/health` answers
**200 whatever its body says** — so a fresh pre-bootstrap instance reporting
`status: "degraded"` still becomes **healthy** and stays reachable, and D5 breaks nothing
in `fast/001.dev-and-container-harness` (which is built before this feature).

That safety rests entirely on the healthcheck asserting the **status code** and never the
**body**. A "hardened" variant that grepped the body for `"status":"ok"` would make a
fresh instance **permanently unhealthy**, and `deployment.md:171-173`'s own rule — *"an
orchestrator that waits on health never routes a user into the window at all"* — would
then mean **nobody can ever reach the bootstrap page to configure the instance**.
FEAT-001 would be unreachable by the very mechanism meant to protect it, and the symptom
would present as a container fault rather than a bootstrap one. So: the healthcheck tests
the status code, deliberately, and must keep doing so. `outcome.md` asks the architect to
record that beside the healthcheck block in `deployment.md`.

### D6 — `require_unconfigured` is a router-level dependency, declared in `routers/bootstrap.py`

`backend-structure.md:209-213`: *"The check is a dependency rather than a check inside
each handler so that adding a bootstrap route cannot forget it."* It is attached to the
**router**, not to the handler, which is precisely what will guard
`fast/003.bootstrap-from-export`'s import route for free.

It is declared **in `routers/bootstrap.py`** rather than in a new shared dependency
module: it is a router-level concern whose only consumers are that router's routes, and
`backend-structure.md`'s Layout names no dependency module. `004` is free to create
whatever home `require_user` and `require_role` want without inheriting a placement this
feature guessed at.

### D7 — `003` defines the role **enum** and not the ladder

`004`'s brief claims "the two-rung role ladder and the `require_role(min_role)` router
dependency" as its own Scope In. But `003` cannot declare the `role` column or write
`'admin'` without the column's value domain, so it defines the two-value enum — and
nothing more. **`003` must not define `ROLE_LADDER` or `require_role`.**

The enum lives in **`backend/app/roles.py`**, a leaf module beside `config.py` and
`ids.py`: `db/schema.py`, `services/`, `models/` and (from `004`) the router dependency
all need the vocabulary, and a top-level leaf keeps `db/` from importing `models/`.
`004`'s planner finds the enum already there and the ladder still to build; `outcome.md`
asks the architect to record the placement.

### D8 — "Applying the registry" is `MetaData.create_all`, inside the creation transaction

`db/drift.py`, `db/sync.py` and Alembic **do not exist** — they are `007`'s, and Alembic
is not a dependency (`001/context.md:81-83`). `003` must not depend on any of them. So
applying the registry here is SQLAlchemy's own `create_all` against the single
`MetaData` in `db/schema.py`, bound to the request's connection **inside the same
`with conn.begin():` block as the administrator insert**.

Two properties this buys, both worth stating:

- **It stays correct as the schema grows.** The registry is the single source of truth
  and every later feature appends its `Table(...)` literal to that same file, so
  `create_all` creates whatever the registry holds at that moment with no per-feature
  edit here. Its create-if-missing behaviour also makes it idempotent.
- **There is no half-bootstrapped instance.** Schema plus first administrator commit
  together or not at all, so the state the guard reads is never "tables but no admin"
  because a request died in the middle.

**That second property depends on the engine running transactional DDL, and step `002`
adds that setting to `app/db/engine.py`.** The first build of this feature found the
gap. Under the pysqlite driver's default (legacy) transaction control, SQLAlchemy's
`begin()` sends no `BEGIN`, and the driver opens a transaction only right before DML. So
`create_all`'s `CREATE TABLE` statements autocommitted, and a failed insert rolled back
the row but left the tables. Being "in the same block" was not enough. The block also has
to be a real SQLite transaction. The user chose to widen step `002` rather than weaken
this decision. The setting applies to the whole engine, so every later
"commit together or not at all" transaction gets the same semantics. The mechanism and
its constraints are in `002.bootstrap-service-and-error.md` and `002.context.md`.

The database **file** needs no explicit creation step: it appears as a side effect of
connecting to the resolved path, and a missing `data_dir` is created rather than raising
(`001/005` DoD-5).

### D9 — US-001.AC-2 is knowingly deferred to `004.authentication-session`

**User decision.** `003` creates the administrator and returns **no cookie**. The
`bootstrap` UI hands off to `/login` with a plain document navigation
(`window.location.assign`), which is how every cross-entry navigation works in this
project (`frontend-structure.md`, "Navigation between entries").

`003` does **not** declare `auth_sessions`, does not mint a token and does not set a
cookie — `004`'s brief claims all three as its own Scope In, and building a session here
would fork the session mechanism across two features.

**The consequence, stated plainly: FEAT-001 is not fully delivered until `004` ships.**
No Definition-of-done item in this feature claims US-001.AC-2, and none may be added to
make the coverage look complete. `outcome.md` records the deferral.

### D10 — The not-ready-yet classification is `003`'s, and it is wider than 502

`002` owns neither this branch nor any 502 policy (`002/context.md:293-294` defers it),
so `003` defines it, in **one named, tested predicate** in
`frontend/src/shared/notReady.ts` rather than inline `if`s in components.

The condition is, in terms of `002`'s D8 synthetic codes: an `ApiError` whose code is
`client_transport_failed` (status `0`), **or** whose code is `client_malformed_error`
with a status of **500 or above**.

**The widening from "502" to "any 5xx with a malformed body" is deliberate.**
`deployment.md`'s passage is about `supervisord` having no wait-for ordering: nginx
serves the bootstrap bundle while uvicorn is not accepting connections, so the bundle's
very first request cannot succeed. 502 is what nginx happens to emit for that, but 503
and 504 from the same proxy, and a connection that dies mid-response, are the *same*
condition — "running but not yet answering". Keying on the exact number would make the
not-ready screen depend on one proxy's choice of status. A backend that is up and
answering the error envelope is **not** matched, because its code is its own domain code
and never a synthetic `client_` one — so this predicate can never swallow a real failure.

It lives in `shared/` beside `apiError.ts` because it classifies an `ApiError` and
nothing about bootstrap, and because `005`'s admin gate needs the same judgement
(`deployment.md:165-170`: "a 502 or a network failure on `/api/me` is not a deny"). It
is a predicate only — it navigates nothing and renders nothing.

### D11 — Retry posture: a fixed 2000 ms re-probe, uncapped, plus a visible manual retry

`deployment.md:146-152` makes the not-ready window a deployment fact, not a bug, and the
bootstrap entry must **retry** rather than treat it as terminal. The plan chooses the
simplest posture that is testable:

- while the entry is in the not-ready state it re-probes `GET /api/health` on a **fixed
  2000 ms interval** — no exponential backoff, no jitter;
- **no attempt cap**, and therefore no terminal dead end: the window is bounded by
  container start (seconds), and a cap would leave a permanently dead screen on the one
  surface an operator has;
- a **visible manual retry control** as well, so the operator is never watching a screen
  with nothing to do;
- the pending timer and the in-flight request are **cancelled on unmount** (a timer
  handle plus an `AbortSignal`), and `002`'s D2 rule applies: an effectful free function
  early-returns on an aborted signal before writing.

Fixed interval over backoff because backoff optimises for a long outage, and this window
is short and self-clearing; fake timers make a fixed interval trivially assertable,
which a jittered backoff is not.

### D12 — Nothing in the `bootstrap` entry calls `notifyFailure`

`002/005:70-78` makes `shared/notifyFailure.ts` the **only** sanctioned notification
channel and scopes it to a failure that *has no place to render*. Every failure in this
entry has one:

- the **not-ready-yet** state and the **refusal** state are full-page in-place renders;
- the **create form**'s failures render in place too — field-shaped ones on their field,
  everything else on a general key shown in an inline `Alert`, which is exactly
  `002`'s D6 field-mapping half of the convention.

A one-shot, irreversible operation on a single full-page form is the worst possible
candidate for a message that disappears after five seconds. So the entry adds **no new
notification call site**, and `002`'s scan that Mantine's notification API is imported by
`notifyFailure.ts` alone stays true unchanged.

### D13 — Per-entry store placement: beside `main.tsx`, in the entry's own folder

`002` ships zero stores, so `003` creates the project's first — and `002` states no
convention for where a store file lives. **This feature sets the precedent later
features follow:** a page's state and draft modules live **under the entry folder,
beside `main.tsx`**, named for what they hold — `bootstrapState.ts`,
`createAdminDraft.ts` — with their pure derivations and their effectful free functions
in the **same module** as the data class they operate on.

Reason: `002`'s D2 makes a store a *data class plus free functions over it*, which is one
subject and belongs in one file; and an entry folder is already the unit of bundling, so
a store that is only ever used by one entry has no business in `shared/`. `outcome.md`
asks the architect to record it in `frontend-structure.md`.

The `002` conventions this feature inherits unchanged: `makeAutoObservable(this, {}, {
autoBind: true })` in the constructor, **observable fields only — no methods and no
computed getters**; derivations are pure free functions taking the data object; effectful
work is a free function taking the data object plus an optional `AbortSignal`, which
`runInAction`s its writes; one store per page via `useState(() => new XState())`, never
`useMemo`; stores passed **explicitly as props**, no React context; components reading
observables wrapped in `observer`.

### D14 — Two assertions from earlier features become false here, and both are deleted deliberately

Neither is an architecture change; both are recorded consequences, here and in
`outcome.md`.

1. **`002`'s pure-data-contract scan clause.** `002/006` DoD-10 asserts there is no
   `makeAutoObservable` and no page-store class anywhere under `frontend/src`. `003`
   creates the first store, so the clause is false. **Per user decision, the clause is
   deleted and not replaced** — the smallest diff was chosen over narrowing the scan.
   Step `004` owns the deletion as an explicit DoD item so it is deliberate rather than
   incidental, and **every other clause of that scan stays intact**. From `003` onward
   the store convention (D13 and `002`'s D2) is **review-enforced, not test-enforced**.
2. **`001`'s registry-emptiness assertion.** `001/005` DoD-7 asserts the registry's table
   collection is **empty**. `003` adds the first `Table`, so that sub-clause is false.
   The same posture applies: step `001` deletes the emptiness sub-clause, keeps the
   enumerability sub-clause (which is the shape `007` walks and is still true), and adds
   its own assertion that `users` is in the registry.

Additionally, any `001`-era expectation about `GET /api/health`'s **body on a fresh
database** changes with D5 and is corrected by step `002`, which owns that test file for
the duration of the step.

### D15 — What `003` writes into `users`, and what it leaves alone

The **whole** table is declared, per `data-model.md`'s authoritative column list, even
though the creation path writes only some of it: the registry is the single source of
truth, and a partially declared table would be drift `007` then reports against itself.
`role` is a single enum column and never an `is_admin` boolean.

The first-run insert sets `id` (minted from the process snowflake generator the app
factory holds on **application state** — never a module global), `username`,
`password_hash`, `role` = `admin` (UC-001), `is_enabled` true, and
`created_at`/`updated_at` as UTC ISO-8601 text. **`rp_language` and `preferred_language`
are left NULL**: they are user-level defaults owned by FEAT-013/UC-047 and this entry
offers no field for them, so inventing a value would be inventing a requirement.

**No duplicate-username path is built.** `username` is unique in the registry, but
`require_unconfigured` makes a second creation unreachable, so there is no
`username_taken` error here — that arrives with FEAT-003's account management (`005`).

### D16 — Credential validation, kept to what is actually required

`docs/product/` states no password policy, so **none is invented**: no length floor
beyond non-empty, no character classes, no strength meter.

- **Client side**: username and password required and non-empty after trimming, plus a
  **confirmation field that must match**. The confirmation is a UI decision, not a
  product requirement, and it is taken because this is a one-shot irreversible operation
  on an instance with no password-reset path anywhere in the product — a typo would
  strand the operator. Its DoD items are structural and cite no AC.
- **Server side**: both fields are non-empty by a pydantic field constraint, which
  answers a violating request with FastAPI's own `422` rather than the domain-error
  envelope. That is a **defensive backstop**, not a rendered path — the form cannot
  submit an empty field — and it deliberately adds **no new domain error code**.

## Vocabulary

| Term | Means here |
|---|---|
| **configured** | a `users` table exists and holds at least one row whose role is `admin` (D3) |
| **unconfigured** | not configured — the only state in which any bootstrap route acts |
| **not-ready-yet** | the backend is starting and cannot answer at all yet (D10); not a failure and not a refusal |
| **refusal** | UC-003: the instance is configured, bootstrap does nothing, and the person is directed to sign in |
| **the offer** | the unconfigured screen: create-new today, with room for import (`fast/003`) |
| **hand-off** | the document navigation to `/login` after creation (D9) |

## Step map

| Step | Subject | Depends on |
|------|---------|------------|
| 001 | the `users` table literal, the `Role` enum, `services/passwords.py`, `argon2-cffi` | — |
| 002 | `already_configured`, the configured predicate, the create-first-administrator transaction, health's delegation, the engine's transactional DDL | 001 (and `001.backend-foundation/005`) |
| 003 | `models/bootstrap.py`, `routers/bootstrap.py` + `require_unconfigured`, router registration | 001, 002 |
| 004 | `shared/notReady.ts`, the entry's store and probe, the three rendered states, the route table | — (backend contract only) |
| 005 | the create-administrator form, its submit path, the hand-off to `/login` | 004 |

Steps `001`–`003` are the backend seam and `004`–`005` the frontend one, which is the
natural split for this feature: the frontend binds to the route contract, not to the
service internals.

## Test conventions inherited

**Backend** (`001/context.md`): tests live in `backend/tests/` as
`test_<module>.py`; `conftest.py` holds the shared fixtures. Decision D4 there governs
the database fixture — **a real `.sqlite` file under `tmp_path`, per test, obtained
through the production engine factory**, never `:memory:` and never session-scoped. An
environment fixture clears every `RPHELPER_*` variable and clears the settings cache
around each test; settings are overridden through that cache or through
`dependency_overrides`, never by monkey-patching a module global. **`003` adds no
setting**, and in particular no admin-seed setting — the first administrator comes from
the operator through the UI (UC-001).

**Frontend** (`002/context.md`): **Vitest** + Testing Library + jsdom, configured in
`vite.config.ts`'s `test` block. Tests live under **`frontend/tests/`, outside `src/`,
mirroring `src/`'s tree**, named `*.test.ts` / `*.test.tsx`. `globals` is **off** —
`describe` / `it` / `expect` are imported explicitly. `frontend/tests/setup.ts` holds
**no fetch stub**: `fetch` is stubbed per test, with no network-mocking library. A
component test rendering Mantine wraps in `shared/AppProviders`. Tests assert **rendered
behaviour**, not internal structure.
