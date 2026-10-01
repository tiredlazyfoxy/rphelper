# Feature 003 — First-run bootstrap · intended documentation changes

Planner section: the `docs/architecture/` changes the architect applies at finalization,
grouped by target file. Nothing here is applied by the planner or the coder.

Two entries at the end are **recorded consequences, not architecture changes**, and are
listed so they are not lost — they must not be dressed up as design decisions.

Entries 14 and 15 were added in a plan revision after the first build. They sit in the
`backend-structure.md` group and are numbered after the rest so that existing
cross-references (entry 4 → entry 13) stay valid.

---

## `docs/architecture/overview.md`

### 1 — Stack decision list: password hashing

- **Section:** the stack decision list.
- **Change:** record **Argon2id via `argon2-cffi`** as the password-hashing choice, with
  the reasoning: a memory-hard, salted KDF whose parameters travel **inside** the stored
  encoded string (`$argon2id$v=19$m=...`), so a parameter change is a rehash-on-verify
  concern and never a schema change; and **the parameters are the library's own current
  defaults, deliberately not hand-picked**, so the project tracks a maintained baseline
  instead of pinning a guess. Record that the algorithm sits behind one module,
  `app/services/passwords.py`, exposing a hash and a verify operation, so it is swappable in
  one file and FEAT-002's login verifies through the same seam.
- **Flip condition:** if `argon2-cffi` stops being maintained, or if a deployment target
  cannot supply its native build, the seam module is the whole of the change surface — and
  the moment the defaults are raised, a **rehash-on-verify** path becomes necessary in the
  login flow (FEAT-002), which no feature has built.
- **Reason:** `docs/architecture/` fixed no hashing algorithm; `brief.md` recorded it as an
  open question and the user settled it. A stack choice with no recorded reason is
  re-litigated.

---

## `docs/architecture/backend-structure.md`

### 2 — The error table: `already_configured`'s status

- **Section:** "The error model", the named-errors table.
- **Change:** record `already_configured`'s `http_status` as **409 Conflict**. Rationale in
  one line: the request is well formed and no identity is being judged — the instance's
  state conflicts with the operation. 403 was rejected because there is no caller identity
  to authorize on an unconfigured-or-not instance; 404 was rejected because hiding the route
  would make UC-003's "directs them to sign in instead" undiagnosable.
- **Reason:** the table names the code, the trigger and the empty `detail` but fixes no
  status, so the plan chose one and the choice belongs in the table rather than only in a
  plan.

### 3 — The bootstrap route surface

- **Section:** "Authorization as router dependencies", beside the `require_unconfigured`
  paragraph.
- **Change:** record the route surface FEAT-001 delivers — `POST /api/bootstrap/create`,
  201, no cookie, request = username + password, response = the new administrator's id
  (decimal string), username and role — and that **`require_unconfigured` is attached to the
  router, not the handler**, and is declared in `routers/bootstrap.py` itself rather than in
  a shared dependency module (the Layout names none). Record that `POST
  /api/bootstrap/import` is the reserved sibling `fast/003.bootstrap-from-export` will add
  under the same guard, inheriting it for free.
- **Reason:** the doc specifies the dependency and the refusal but no path, and the path is
  now real and is what `fast/003` will extend.

### 4 — `/api/health` on a pre-bootstrap instance

- **Section:** `/api/health`.
- **Change:** record the triple a genuinely pre-bootstrap instance answers once `users` is
  in the registry: `configured: false`, `schema: "missing"`, `status: "degraded"` — because
  the roll-up gives a non-`"ok"` schema precedence, and a declared table really is absent.
  Record the consequence for clients: **the bootstrap entry branches on `configured` alone
  and never on `status`**, and `status: "unconfigured"` is the narrower case of a database
  whose tables exist with no administrator row in them.
- **Also record, in one line here, that the endpoint answers HTTP 200 whatever the roll-up
  says**, and cross-reference entry 13 — the compose healthcheck depends on exactly that,
  and the two facts are read together.
- **Reason:** "degraded" on a brand-new instance reads like a fault and will be reported as
  one. The doc already designates `configured` as FEAT-001's signal; this makes the
  interaction with the roll-up explicit rather than something each reader re-derives.

### 5 — Where the role enum lives, and what is still FEAT-002's

- **Section:** "Authorization as router dependencies", or Layout.
- **Change:** record that the two-value role enum lives in **`app/roles.py`**, a leaf module
  beside `config.py` and `ids.py`, because `db/schema.py`, `services/`, `models/` and the
  router dependency all need the vocabulary and a top-level leaf keeps `db/` from importing
  `models/`. Record that FEAT-001 declares **only** the enum, and that `ROLE_LADDER` and
  `require_role(min_role)` remain FEAT-002's to add — naturally beside it in the same
  module.
- **Reason:** the doc shows `ROLE_LADDER` and `require_role` in a snippet with no module
  named, and the split between "the enum" and "the ladder" now runs between two features.

### 6 — Registry creation is `create_all`, and it is request-time

- **Section:** "Schema evolution — the registry is the truth, the administrator applies",
  as a fifth fact beside the four explicit negatives.
- **Change:** record that FEAT-001's bootstrap applies the registry with SQLAlchemy's own
  create-if-missing creation against the single `MetaData` in `db/schema.py`, bound to the
  request's connection and **inside the same transaction as the first administrator's
  insert**, so no half-bootstrapped instance is reachable. State plainly that this is
  **neither DDL at startup nor FEAT-005's admin-triggered sync**: it is a one-time
  operator-triggered operation on an instance that has no schema at all, it uses no Alembic
  and no `db/sync.py`, and the "no DDL at startup" rule is untouched. Cross-reference
  entry 14: "inside the same transaction" is only true because of the engine's
  transactional-DDL setting.
- **Reason:** "the registry is applied at bootstrap" and "there is no automatic upgrade at
  startup" look contradictory until the distinction is written down, and the doc's four
  negatives are exactly where a reader will look for it.

### 7 — `password_hash` stores a self-describing encoded string

- **Section:** the error-model-adjacent prose is wrong for this; put it beside the secret
  pointer pattern, or cross-reference from `data-model.md`'s `users` (entry 8).
- **Change:** one line: `users.password_hash` holds `argon2-cffi`'s own encoded string, so
  the algorithm, version and parameters live **in the value** and no schema column records
  them.
- **Reason:** it is the reason a parameter change is not a migration, and the reason there is
  no `hash_algorithm` column to add later.

### 14 — The engine runs pysqlite with transactional DDL

- **Section:** "Database access", as a fourth item in the "on every connection" list, or
  as a paragraph directly after the list. Cross-reference it from "Persistence access —
  SQLAlchemy Core, not the ORM", reason 1 (explicit transaction scoping).
- **Change:** record that `db/engine.py` runs the pysqlite driver with **transactional
  DDL**: the driver's own implicit transaction handling is off, so it never opens or
  commits a transaction by itself, and SQLAlchemy's `begin` sends the real `BEGIN`. So a
  `with conn.begin():` block covers **every** statement inside it, `CREATE TABLE`
  included, and savepoints behave. The reference is SQLAlchemy's documented "pysqlite
  transactional DDL" configuration. Record the constraints that come with it: the
  per-connection PRAGMAs still run outside any transaction (`journal_mode = WAL` cannot be
  entered inside one, and `foreign_keys` is a no-op inside one), so a driver mode that
  keeps a transaction open at all times is excluded, and the connection dependency still
  opens no transaction.
- **Reason:** under the driver's default (legacy) transaction control, SQLAlchemy's
  `begin()` sends no `BEGIN`, and the driver opens a transaction only right before DML, so
  DDL autocommits. FEAT-001's first build found this: a failed first-administrator insert
  rolled back the row and left the tables, which is exactly the half-bootstrapped state
  entry 6 promises cannot exist. The doc's claim that "these writes commit together or not
  at all" is a `with conn.begin():` block (reason 1) is only true with this setting, and
  settle, memo-plus-embedding, account-disable and FEAT-005's DDL all rely on it. It is an
  engine-wide property and not a bootstrap special case, so that the process has one
  transaction semantics.
- **Flip condition:** if the project moves off the stdlib `sqlite3` driver, or a later
  SQLAlchemy/Python release makes transactional DDL the default, re-check this setting and
  drop it if it becomes redundant. The DDL-rollback test added with FEAT-001
  (`backend/tests/test_db_engine.py`) is the check.

### 15 — `already_configured` carries a default human-readable message

- **Section:** "The error model", beside the named-errors table's `already_configured`
  row, or as a one-line rule under the wire-shape example.
- **Change:** record that `already_configured`, raised with no arguments, as
  `require_unconfigured` raises it, renders a **non-empty human-readable `message`** that
  the subclass itself supplies, so the wire body matches the documented shape, where
  `message` is a string. Record that the default lives on the subclass: the base class and
  its handler have no class-level default message, and adding one there would change what
  every other error renders.
- **Reason:** the wire example shows `message` as a string, but the base class stores the
  message exactly as given, so an error raised bare rendered `"message": null`. FEAT-001's
  first build shipped that null on its 409. Whether other named errors should follow the
  same subclass-default pattern is the architect's call. This feature decides it only for
  `already_configured`.

---

## `docs/architecture/data-model.md`

### 8 — `users`, as built

- **Section:** `users`.
- **Change:** record what FEAT-001 declares and what it writes: the whole column list is
  declared even though bootstrap writes only part of it (the registry is the single source of
  truth and a partial table would be drift FEAT-005 reports against itself);
  `rp_language` and `preferred_language` are **nullable and left NULL** by the first-run
  insert, because they are FEAT-013/UC-047's and bootstrap offers no field for them;
  `username` is unique but **no duplicate-username path exists yet** because
  `require_unconfigured` makes a second creation unreachable — that arrives with FEAT-003.
  Add the `password_hash` line from entry 7 or cross-reference it.
- **Reason:** the column list is authoritative but silent on nullability and on who writes
  which column, and the next writer of this table (FEAT-003) needs both.

---

## `docs/architecture/frontend-structure.md`

### 9 — The `bootstrap` entry's boot shape

- **Section:** "Per-entry responsibilities", as a subsection mirroring the `admin` entry's
  "Boot sequence".
- **Change:** record the entry's shape: one `GET /api/health` on mount, reading
  **`configured` alone**; five states — probing (neither offer nor refusal rendered), the
  offer, the already-configured refusal with a real anchor to `/login`, not-ready-yet, and a
  non-not-ready failure; **no `basename`**; no stylesheet import of its own; and no API
  surface beyond `/api/health` and the bootstrap routes. Record that the refusal is UX over a
  server-side guard, exactly as the admin gate is: `require_unconfigured` is the boundary.
- **Reason:** the doc explains **why** this entry is separate but describes no boot shape,
  and the `admin` entry's equivalent section is the precedent readers will compare against.

### 10 — The not-ready-yet classification, as a shared rule

- **Section:** "The API client", after the 401/403 rules.
- **Change:** record the classification and its home: `shared/notReady.ts` exports one pure
  predicate answering whether a thrown value is the not-ready-yet condition — the
  transport-failure synthetic code, **or** the malformed-body synthetic code at status 500 or
  above. Record the widening from 502 with its reason (`supervisord` has no wait-for
  ordering; 502/503/504 and a died-mid-response are the same "running but not answering"
  condition, and keying on one number makes the screen depend on one proxy's choice), and
  that a well-formed backend envelope can never match because its code is a backend code.
  Record the retry posture FEAT-001 chose: a fixed 2000 ms re-probe, uncapped, no backoff,
  plus a visible manual retry, cancelled on unmount.
- **Reason:** `deployment.md` states the requirement in two places (the bootstrap entry and
  the admin gate's "a 502 is not a deny") and no doc says what the rule *is*. This is the
  precedent FEAT-002/FEAT-003's admin gate points at instead of re-deriving.

### 11 — Per-entry store file placement

- **Section:** "State — MobX 6, per-page stores, no context".
- **Change:** record the precedent FEAT-001 sets: a page's state and draft modules live
  **under the entry's own folder beside `main.tsx`** (`src/bootstrap/bootstrapState.ts`,
  `src/bootstrap/createAdminDraft.ts`), with the pure derivations and the effectful free
  functions in the **same module** as the data class they operate on. Reason to record: a
  store is a data class plus free functions over it, which is one subject; and the entry
  folder is already the unit of bundling, so a single-entry store has no business in
  `shared/`.
- **Reason:** the doc fixes the MobX convention but not where the file lives, and this is the
  project's first store — the next four features will copy whatever it did.

### 12 — `notifyFailure` is not the channel for a full-page state

- **Section:** "The API client" (the transient-notification sentence) or
  `ui-conventions.md`'s notifications rule, whichever the architect judges to own it.
- **Change:** one clarifying line, with FEAT-001 as the worked example: a failure that has a
  full-page state of its own — a not-ready-yet screen, a refusal, a form's inline alert — is
  rendered there and **does not** also raise a notification. The `bootstrap` entry adds no
  notification call site at all.
- **Reason:** the existing rule is correct but its boundary is read as "every thrown error
  gets a toast", and this entry is the first place where the distinction is load-bearing.

---

## `docs/architecture/deployment.md`

### 13 — The healthcheck asserts the HTTP status and never the body

- **Section:** beside the compose healthcheck block (`deployment.md:130-131`), and not only
  in `backend-structure.md`'s `/api/health` entry above.
- **Change:** record that the healthcheck is `curl -f` against `/api/health` and therefore
  tests the **HTTP status code**, never the response body — and that this is **deliberate and
  load-bearing, not an implementation detail**. `/api/health` answers **200 whatever its
  roll-up says**, so once FEAT-001 puts `users` in the registry a fresh pre-bootstrap
  instance reporting `status: "degraded"`, `configured: false`, `schema: "missing"` (entry 4)
  still becomes **healthy** and stays reachable.
  State the consequence of changing it: a variant that inspected the body for
  `"status":"ok"` would make a fresh instance **permanently unhealthy**, and this doc's own
  rule that *"an orchestrator that waits on health never routes a user into the window at
  all"* (`deployment.md:171-173`) would then mean **nobody can ever reach the bootstrap page
  to configure the instance**. FEAT-001 would be unreachable by the mechanism meant to
  protect it, and the symptom would present as a container fault rather than a bootstrap one.
- **Reason:** `fast/001.dev-and-container-harness` is built **before** FEAT-001, so the
  harness is written while a body-inspecting healthcheck still looks like a harmless
  tightening. The invariant only becomes visible once `users` is in the registry, which is
  after that feature has shipped — so it has to be written down where the harness's author
  and any later "hardener" will read it.

---

## Recorded consequences — not architecture changes

### C1 — US-001.AC-2 is deferred to `004.authentication-session`

FEAT-001 ships **without** signing the operator in. `003` creates the administrator and
returns no cookie; the `bootstrap` UI hands off to `/login` with a document navigation, and
the operator signs in there. `003` declares no `auth_sessions` table, mints no token and sets
no cookie — `004`'s brief claims all three as its own Scope In, and building a session here
would fork the session mechanism across two features.

**Consequence, stated plainly: FEAT-001 is not fully delivered until `004` ships.** No DoD
item in this feature claims US-001.AC-2. When the feature is finalized, `docs/product/`'s id
registry should show US-001 as **partially delivered**, naming `004.authentication-session`
as the plan that owns AC-2 — a `/product-spec` action, not an architecture edit.

### C2 — Two earlier assertions are deleted, deliberately

- **`002/006` DoD-10's pure-data-contract clause** (no `makeAutoObservable`, no page-store
  class under `frontend/src`) is **deleted and not replaced**, in
  `frontend/tests/conventions.test.ts`, by step `004` — this feature creates the project's
  first store. Per user decision the smallest diff was chosen over narrowing the scan, so
  **from `003` onward the store convention is review-enforced, not test-enforced**. Every
  other clause of that scan stays.
- **`001/005` DoD-7's registry-emptiness sub-clause** is deleted, in
  `backend/tests/test_db_schema.py`, by step `001` — this feature declares the first
  `Table`. The enumerability sub-clause stays, because it is still true and is the shape
  `007` walks.

Both are consequences of a foundation feature's criteria being true only until the first real
feature lands. Neither is an architecture change, and neither should be recorded as one.

---
Status: Applied 2026-10-01 — /architect finalization (with /product-spec finalization the same day)
Applied items: 14 (entries 1–4, 6–15; entries 3 and 9 with modification)
Rejected items: 1 (entry 5 — superseded, not applied)
Notes: entry 3 modified — `POST /api/bootstrap/create` answers 201 and sets the session cookie inside the same transaction (per 004 C1); body still carries no token. Entry 9 modified — the post-create hand-off is a document navigation to `/` (the refusal still links to `/login`). Entry 5 superseded by 004 entry 4 (`roles.py` = enum + ladder + pure comparison; `dependencies.py` = the FastAPI dependencies and cookie writers). Entry 14 additionally records the status.md consequence: an autobegun read holds a real deferred BEGIN until rollback/commit or pool reset, so a read followed by `begin()` on one connection must end the read first. C1/C2 are not doc changes.
