# Backend structure

**Realizes:** FEAT-001, FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-008,
FEAT-009, FEAT-010, FEAT-013, FEAT-018, FEAT-019, FEAT-020, UC-003,
UC-006..UC-015, UC-027, UC-035, UC-037, UC-050, UC-065, UC-066, UC-071, UC-078, UC-080,
UC-083, UC-084, UC-085, UC-086, UC-087, US-006.AC-3, US-018.AC-6, US-018.AC-7,
US-132, US-134, US-135, US-140

FastAPI application layout, the routers/services split, the id and JSON
boundaries, configuration and secrets, and the error model that carries typed
failures to the SPA. Commands (`pytest`, `mypy app`, `ruff check .`) are in the
root `CLAUDE.md`.

## Layout

```
backend/
  .venv/
  app/
    main.py              # app factory, router registration, lifespan
    config.py            # pydantic-settings Settings + lru_cache accessor
    logging.py           # loguru sink configuration + the InterceptHandler;
                         #   called ONCE from main.py (deployment.md)
    ids.py               # the snowflake generator — see below
    secrets.py           # "$ENV_VAR" pointer resolution
    errors.py            # typed error hierarchy + exception handlers
    roles.py             # Role enum + ROLE_LADDER + one pure "at least this
                         #   rung" comparison; no fastapi (plan 003, plan 004)
    dependencies.py      # CurrentUser, require_user, require_role(min_role)
                         #   and the session-cookie set/clear writers (plan 004)
    db/
      engine.py          # connection, PRAGMAs, sqlite-vec extension load
      schema.py          # the table-definition registry (data-model.md)
      drift.py           # PRAGMA introspection vs the registry (FEAT-005)
      sync.py            # the DDL executor: Alembic batch ops, admin-triggered
                         #   only; resolves the table name itself and may
                         #   import drift.py, never the reverse — see
                         #   "Schema evolution" below
    routers/
      health.py          # /api/health
      bootstrap.py       # FEAT-001
      auth.py            # FEAT-002, and /api/me
      admin_users.py     # FEAT-003 — /api/admin/users (plan 005)
      admin_llm.py       # FEAT-004 — /api/admin/llm-servers (plan 006)
      admin_db.py        # FEAT-005 — /api/admin/database (plan 007)
      characters.py      # FEAT-006
      setups.py          # FEAT-007
      sessions.py        # FEAT-008, FEAT-013
      stream.py          # FEAT-009 + FEAT-010: the record, the zone, settle,
                         #   re-open, and the one SSE route
      memos.py           # FEAT-012
      search.py          # FEAT-017
      transfer.py        # FEAT-018
    services/
      health.py                  # /api/health's probe SQL — NOT a domain service; see
                                 #   "Routers versus services" (decided in plan 001)
      bootstrap.py  auth.py  users.py
      passwords.py               # the password-hashing seam: hash + verify (plan 003)
      llm_registry.py            # servers, models, the probe primitive, designation,
                                 #   and BOTH use-time validators (plan 006)
      config_resolver.py         # R1's two chains
      memo_chain.py              # R2
      characters.py  setups.py
      sessions.py                # incl. start-a-session-by-writing (UC-080):
                                 #   create + seed the zone in ONE transaction
      messages.py                # append to the zone, edit text, file a partner block
      settle.py                  # settle + re-open — the ONLY writers of raw messages
      parens.py                  # the (( )) parser: classify + strip. Pure, no I/O
      compose.py                 # the compose loop, orchestrates llm + tools
      translation.py             # FEAT-011
      search/
        ports.py                 # the narrow search port (search-and-retrieval.md)
        hybrid.py                # vec + FTS + RRF
        memo_search.py  session_search.py  my_search.py
      llm/
        client.py                # one OpenAI-compatible client, httpx.AsyncClient;
                                 #   also declares the probe-outcome value set
                                 #   (plan 006 — see "The first async code")
        frames.py                # SSE frame emission
        tools.py                 # the three tool definitions + dispatch
      transfer.py                # export/import
    models/                      # pydantic request/response models; ids.py holds
                                 #   the id aliases, secret_ref.py the "$"-pointer
                                 #   field type (plan 006)
  tests/
```

`routers/entries.py` and `routers/discussions.py` are **gone**, with the
`discussions` table (`data-model.md`); `services/entries.py` and
`services/discussion.py` go with them. `services/llm/stream.py` is renamed
`frames.py` so that `routers/stream.py` is the only `stream` module in the
backend — two modules with one name across two packages is an import ambiguity
nobody needs.

## The id generator — `app/ids.py`

**Realizes:** FEAT-018, FEAT-019

Every primary key in RPHelper is a snowflake minted in application code before
the INSERT. The bit layout, the fixed epoch, the node-id rule and the
cross-instance qualifier are in `data-model.md`'s Identifiers section and are not
restated here. What belongs here is where the code lives and what it guarantees.

**It sits at `app/ids.py`, beside `config.py` and `secrets.py` — not in
`services/`.** It is infrastructure, not a domain service: it takes no `user_id`,
enforces no rule from `domain-rules.md`, and every service that inserts anything
needs it. Filing it under `services/` would make one service the hub every other
service imports from, in the one layer that exists to hold independent,
plain-argument domain logic.

**Not in `db/` either.** It opens no connection and names no table. Filing it
with database access would imply the database issues ids, which is exactly what
this scheme removes.

Guarantees:

- **Process-local and thread-safe.** Its state is two values — the last
  millisecond issued and the sequence within it — behind a lock. uvicorn serves
  requests on a thread pool, so two inserts can land in the same millisecond; an
  unlocked generator hands out the same id twice.
- **The node id comes from config** (`Settings.node_id`, default 0), read once at
  construction. One generator instance per process, held on application state —
  which is the code-level half of `data-model.md`'s "exactly one generator
  process per node id" deployment guarantee.
- **A backwards clock refuses to issue and raises.** Waiting out the drift and
  carrying on both mint duplicates. It surfaces as an operational fault (a 500),
  not as a domain failure the SPA is expected to render.
- **The backwards-clock exception is NOT a `DomainError` subclass**, and the
  non-relationship is deliberate (decided in plan 001). It is an operational
  fault — a 500 — and a `DomainError` is by definition something the SPA is told
  to render (the error model below). It is exactly the kind of class someone later
  "tidies" into the hierarchy; doing so would dress an operational fault as a
  domain failure with a wire code the UI has no rendering for.
- **Sequence exhaustion blocks until the next millisecond** (decided in plan 001).
  More than 4096 ids in one millisecond waits out the millisecond and continues.
  The two rejected alternatives each fail worse: wrapping the sequence mints a
  duplicate, and raising turns an ordinary write burst into an error the caller
  cannot act on. The wait re-reads the clock, so a backwards step observed during
  it still raises.
- **Time is read through an injectable clock** (decided in plan 001) — the
  generator is constructed with a milliseconds clock that defaults to the system
  clock. That is the only seam by which the backwards-clock refusal and the
  exhaustion wait are testable at all; both are silent-failure territory
  (a duplicate id, an untestable refusal), which is why the seam is recorded
  rather than left an implementation detail.

## The JSON id boundary — every id crosses the wire as a string

**This is the most forgettable rule in the doc set, so it gets its own section
rather than a bullet inside `models/`.**

An id is an `int` in SQLite and in Python, and a **decimal string** in every JSON
payload — request bodies, response bodies, `detail` objects and SSE frames alike.
**Nothing in the API surface exposes an id as a JSON number.** `data-model.md`
holds the reason: a snowflake passes `Number.MAX_SAFE_INTEGER` about 25 days
after the epoch, so an id that reaches JavaScript as a number silently rounds,
possibly onto another row's id.

`models/` is where the conversion happens and the only place it happens:

```python
SnowflakeOut = Annotated[int, PlainSerializer(str, return_type=str)]
SnowflakeIn  = Annotated[int, BeforeValidator(lambda v: int(v))]
```

- **Response models serialize id-typed fields to `str`; request models parse
  `str` back to `int`.** Every id field uses one of the two aliases; a bare `int`
  on a model is the defect.
- **No handler hand-rolls it.** A route that returns a plain `dict` or
  `JSONResponse` bypasses `models/` and therefore bypasses this rule. Routes
  return pydantic models.
- **It covers the places nobody thinks of**: an id inside a `DomainError`'s
  `detail`, and the `message_id` on the SSE `done` frame
  (`llm-and-streaming.md`). Those are JSON on the wire and are bound by the same
  rule.
- **It covers path parameters too** (plan 005). An id in a path is declared with
  the inbound annotated alias from `models/ids.py`, **never as a bare `int` path
  type and never as a `str` the handler calls `int()` on**.
  `/api/admin/users/{user_id}` was the first route with an id in its path; a bare
  `int` happens to work there and quietly moves the boundary out of `models/`.
- The frontend half — **a TypeScript `id: number` anywhere is a defect** — is in
  `data-model.md` and `frontend-structure.md`.

## Routers versus services — the split, and why it is strict

**Routers** own HTTP and nothing else: path and method, request/response pydantic
models, authentication and authorization dependencies, status codes, and turning
a typed domain error into an HTTP response. A router contains no business rule
and issues no SQL.

**Services** own domain rules and data access. A service takes plain arguments
and returns plain results or raises a typed error; it never imports `fastapi`,
never sees a `Request`, and never knows a status code.

Two reasons this is worth being strict about here:

- **Isolation is a query-level property.** R5 requires every read path to be
  scoped by owning user in the query itself. That is auditable only if all SQL is
  in one layer — a single `SELECT` that leaked into a router would sit outside
  wherever the scoping convention is reviewed.
- **The pipeline's air gap** (`docs/plans/CLAUDE.md`) wants domain rules testable
  without a transport. Services that take plain arguments are testable from the
  spec alone; router-embedded rules force a test-coder to reason about HTTP to
  test a memo-chain rule.

Dependency direction is one-way: `routers → services → db`. Nothing in `services`
imports from `routers`. `models/` is imported by both and imports neither.

**`services/health.py` is not a domain service, and is not an exception to the
split either** (decided in plan 001). It enforces no rule from `domain-rules.md`
and takes no `user_id`. It exists only because `/api/health`'s probe issues SQL
and the split forbids a router from doing so: the router calls the probe with a
connection and the registry, and the probe returns a plain result. A reader
finding it in `services/` should read it as the split applied to its first
router, not as a domain-shaped carve-out.

### Authorization as router dependencies

Three dependencies, and every route uses exactly one:

| Dependency | Grants | Used by |
|---|---|---|
| `require_unconfigured` | only while no database/admin exists | `bootstrap.py` (UC-003) |
| `require_user` | any authenticated, enabled account; yields `user_id` | all roleplayer routers |
| `require_role(min_role)` | authenticated, enabled, and **at least** `min_role` on the ladder | `admin_*.py` routers, as `require_role(Role.admin)` |

**`require_role` is a dependency *factory*, not a fixed dependency.** It takes a
minimum role and returns the dependency callable, which resolves the caller from
the session cookie and compares their role against the numeric ladder in
`domain-rules.md`:

```python
# app/roles.py — no fastapi import
ROLE_LADDER: dict[Role, int] = {Role.roleplayer: 0, Role.admin: 1}

# app/dependencies.py
def require_role(min_role: Role) -> Callable[..., CurrentUser]: ...
```

A factory rather than one `require_admin` dependency because the check every
route wants to express is a **threshold** — "at least this rung" — so a new rung
is one ladder entry rather than a new dependency per role plus an audit of which
routes should have gained it.

#### Where the vocabulary and the dependencies live — two leaf modules

Decided in plan 004, **correcting what plan 003's outcome proposed** (that
`ROLE_LADDER` and `require_role` would sit "naturally beside" the enum in the
same module). Written down so the two features' proposals are not re-mixed:

- **`app/roles.py` holds the two-value `Role` enum, `ROLE_LADDER` and one pure
  "at least this rung" comparison, and stays free of `fastapi`.** It is a
  top-level leaf beside `config.py` and `ids.py` because `db/schema.py`,
  `services/`, `models/` and the dependencies all need the vocabulary, and a
  top-level leaf keeps `db/` from importing `models/`. FEAT-001 declared the
  enum; FEAT-002 added the ladder and the comparison.
- **`app/dependencies.py` holds `CurrentUser`, `require_user`,
  `require_role(min_role)` and the two session-cookie writers (set and clear).**
  A top-level leaf beside `config.py`, `ids.py`, `errors.py` and `roles.py`.

Why not "in the same module" as the enum: **`db/schema.py` imports
`app/roles.py`** for the `role` column's value domain, so a FastAPI dependency
factory in `roles.py` would drag `fastapi` into `db/` transitively. Why not
inside a router either: the dependencies' consumers are **many** routers, so one
router owning them would make every other router import from a sibling — unlike
`require_unconfigured`, whose only consumer is `routers/bootstrap.py`, which is
why it lives there. The cookie writers sit beside the dependencies because all
four share one fact — the cookie's name and flags — and are used by two routers
(`auth.py` and `bootstrap.py`).

**What `require_user` resolves**, stated because three docs depend on it:

```
cookie → SHA-256 digest → an auth_sessions row, not revoked, not expired
       → join users → the account must be enabled
       → CurrentUser { id, username, role }   # role read LIVE from users
```

Consequence: **a role change or a disable takes effect on the caller's next
request**, with no session rewrite. `auth_sessions` carries no `role` column
(`data-model.md`), so there was never a cached role to go stale. `require_role`
runs the same resolution and then compares the rung.

`require_role(Role.admin)` sits on **every** route in `admin_users.py`,
`admin_llm.py` and `admin_db.py` — as a router-level dependency, not per handler,
so adding an admin route cannot forget it. **All three consumers now exist**:
`admin_users.py` was the factory's first (plan 005 — it shipped with zero
consumers in plan 004), `admin_llm.py` the second (plan 006), `admin_db.py` the
third and last (plan 007). The property proved by test is that a route on such a
router declaring nothing of its own is still refused. The frontend's pre-mount gate
(`admin-surfaces.md`) and the hidden menu item (`workspace-shell.md`) are UX
only; this is the boundary. Every route behind it is additionally bound by R5: it
returns no user content and no count derived from it.

`require_user` yields the `user_id` that every service call is scoped by. A
service that touches user-owned data takes `user_id` as a **required positional
argument** — not an optional filter, not a keyword with a default. A forgotten
scope becomes a type error rather than a privacy incident.

`require_unconfigured` implements UC-003 directly: once the instance is
configured, every bootstrap route refuses (create-new and import alike). The
check is a dependency rather than a check inside each handler so that adding a
bootstrap route cannot forget it.

#### The bootstrap route surface — FEAT-001

**Realizes:** FEAT-001, UC-001, UC-003

| Route | Answers | Notes |
|---|---|---|
| `POST /api/bootstrap/create` | **201** + the new administrator's identity — id as a decimal string, username, role — **and `Set-Cookie`** | request = username + password, nothing else accepted onto the account; **the body carries no token** |
| `POST /api/bootstrap/import` | — | **reserved**, not built: `fast/003.bootstrap-from-export` adds it under the same guard (UC-002, deferred) |

- **The create signs the operator in.** It mints an `auth_sessions` row **inside
  the same transaction** that applies the registry and inserts the first
  administrator, and sets the session cookie on its 201 through the cookie
  writer in `app/dependencies.py` (plan 004, which closed the deferral plan 003
  shipped with). The body still carries no token or session field — the cookie
  is the only carrier, exactly as for login.
- **`require_unconfigured` is attached to the router, not the handler**, and is
  declared in `routers/bootstrap.py` itself rather than in a shared module: its
  only consumer is that router. A router-level guard is what lets `fast/003`'s
  import route inherit the refusal for free.
- `already_configured` answers **409** (the per-code status record below).

#### The admin route surfaces — FEAT-003, FEAT-004, FEAT-005

**Realizes:** FEAT-003, FEAT-004, FEAT-005, UC-006..UC-015, UC-087

All three live under **`/api/admin/`**, one prefix per router, each with
`require_role(Role.admin)` attached once at router level. No document fixed the
paths before the plans did; they are recorded rather than left to be discovered,
as the bootstrap and auth surfaces are.

**`/api/admin/users` — `routers/admin_users.py` (plan 005).** Six routes, each
answering with an account model, none taking a query parameter:

| Route | Answers |
|---|---|
| `GET /api/admin/users` | the account list |
| `POST /api/admin/users` | **201**, the created account |
| `POST /api/admin/users/{user_id}/disable` | the account |
| `POST /api/admin/users/{user_id}/enable` | the account |
| `POST /api/admin/users/{user_id}/password` | the account |
| `POST /api/admin/users/{user_id}/role` | the account (UC-087, US-140) |

**Named action routes, not one `PATCH /api/admin/users/{id}`**, so that the
disable's transaction, the self-target refusal and the password hash each hang
off their own body and rule.

**`/api/admin/llm-servers` — `routers/admin_llm.py` (plan 006).** Nine routes:

| Route | Answers |
|---|---|
| `GET /api/admin/llm-servers` | the list, **each row carrying its enabled model names** |
| `POST /api/admin/llm-servers` | **201** |
| `PATCH /api/admin/llm-servers/{server_id}` | the registration |
| `DELETE /api/admin/llm-servers/{server_id}` | **204** |
| `POST /api/admin/llm-servers/{server_id}/test` | **200 even for a failing outcome** ("The connection probe" below) |
| `GET /api/admin/llm-servers/{server_id}/available-models` | the offered names, or **502** `llm_unreachable` |
| `POST /api/admin/llm-servers/{server_id}/models` | replaces the enabled set |
| `POST /api/admin/llm-servers/{server_id}/embedding-model` | designate (measures the dimension — `admin-surfaces.md`) |
| `DELETE /api/admin/llm-servers/{server_id}/embedding-model` | clear the designation |

Four decisions embedded in it:

- **`PATCH`, not FEAT-003's named-action pattern.** A registration is one entity
  with one rule, and the API-key contract is literally "which fields were
  supplied" (`admin-surfaces.md`'s round-trip rule).
- **`POST`, not `PUT`, for the enabled set**, because the shared frontend client's
  method union has no `PUT`, and adding one for a single call site was out of
  scope.
- **No `GET /{server_id}/models`.** The enabled names ride on the list payload,
  which is what makes failed-probe resilience structural (`ui-conventions.md`).
- **The clear-designation path is server-scoped**, so it cannot collide with
  `{server_id}` in the route table.

**`/api/admin/database` — `routers/admin_db.py` (plan 007).** Three routes, all
answering **200**, all taking **no body and no query parameter**:

| Route | Answers |
|---|---|
| `GET /api/admin/database/tables` | the whole drift report |
| `POST /api/admin/database/tables/{table_name}/create` | the per-table report **re-derived after the apply** |
| `POST /api/admin/database/tables/{table_name}/sync` | the same |

- **Each apply answers with the re-derived row**, giving US-018.AC-2 a
  server-side witness beside the page's re-load.
- **`{table_name}` is validated by lookup in the registry inside `db/sync.py`,
  never in the router**, and the raw string is never interpolated into SQL — only
  the registry's own `Table` object reaches the DDL. That is what makes a non-id
  path parameter safe here, and it is the one thing a later contributor could
  undo by "simplifying" the lookup into the handler.
- **Two routes rather than one `apply`**, because the UI offers them under
  different conditions and only one of the two can lose data.
- **The one admin route family not keyed on a snowflake** — its wire carries no
  id at all, so the JSON id boundary has no call site here.

## The authentication surface — FEAT-002

**Realizes:** FEAT-002, UC-004, UC-005, US-006.AC-3

Owned by `routers/auth.py` under the `/api` prefix:

| Route | Answers | Notes |
|---|---|---|
| `POST /api/auth/login` | **200** + the caller's identity (id as a decimal string, username, role), **and `Set-Cookie`** | no authorization dependency; **never answers 401** (the error model's `invalid_credentials` reasoning); the body carries no token |
| `POST /api/auth/logout` | **204**, cookie cleared | **idempotent and carries no `require_user`** — the same answer whether or not a live session resolved; revokes the **calling** session only |
| `GET /api/me` | as documented below | real since FEAT-002; its 401-on-disabled is mechanically true through `require_user` |

The identity model is **one model serving both `GET /api/me` and the login
route**. **There is no session-refresh route** (below).

**The refusal is uniform** (US-006.AC-3): an unknown username, a wrong password
and a **correct password on a disabled account** all produce the same
`invalid_credentials` refusal — same code, status and message — so a login
attempt never learns whether an account exists or is disabled.

### Password hashing — `services/passwords.py`

The one seam for the algorithm: a hash operation and a verify operation, used by
FEAT-001's first-administrator insert and FEAT-002's login alike. The decision —
**Argon2id via `argon2-cffi`, at the library's own defaults** — and its flip
condition are in `overview.md`'s stack list.

**`users.password_hash` holds `argon2-cffi`'s own encoded string**
(`$argon2id$v=19$m=...`), so the algorithm, version and parameters live **in the
value** and no schema column records them. That is why a parameter change is not
a migration, and why there is no `hash_algorithm` column to add later.

### Session lifetime — absolute 720 hours, no sliding, no refresh route

`auth_sessions.expires_at` is written **once, at login** (and at bootstrap
create), from `Settings.session_ttl_hours` (default 720), and is **never
moved**. There is consequently **no session-refresh route** — the plan 004 brief
named one and the plan dropped it deliberately.

Reason: SQLite has a **single writer**, and an SSE compose exchange holds a
request open for the length of a generation. Extending a session on every
authenticated request would turn **every read into a write** and put the busiest
path in the product behind the one lock the whole database shares.

**Flip condition:** if sessions ever need to survive activity beyond the absolute
window — a product requirement for "stay signed in while working", or a TTL short
enough that people are logged out mid-roleplay — sliding expiry becomes worth the
writes, and the cheapest form is a bounded touch (rewrite `expires_at` at most
once per N minutes) rather than a write per request.

### The session token — opaque and random, stored as a SHA-256 digest

`auth_sessions.token_hash` holds a **SHA-256 digest** of a **32-byte
`secrets.token_urlsafe`** token. The plaintext exists **only in the cookie**;
lookup is by digest. The token is **never logged**.

**Deliberately not Argon2**, although the codebase already depends on it for
passwords. Argon2 exists to make **low-entropy human passwords** expensive to
guess; a 256-bit random token has nothing to guess, and running a memory-hard KDF
on **every authenticated request** would pay a deliberately expensive
computation for no gain. The digest is what makes a stolen database file useless
for replaying live sessions, which is the whole of the requirement. "Argon2 for
passwords, SHA-256 for tokens" is the difference between the two inputs, not an
inconsistency — and the "fix" would be a real performance defect.

### The session cookie's flags

Written by the one setter in `app/dependencies.py`; each flag has a reason:

| Flag | Value | Why |
|---|---|---|
| name | `Settings.session_cookie_name` | never a literal |
| `HttpOnly` | on | there is no token JavaScript can read — which is why the admin gate is a server round-trip (`admin-surfaces.md`) |
| `SameSite` | `Lax` | single origin in both topologies (`overview.md`) |
| `Path` | `/` | it must reach all four entries |
| `Max-Age` | the TTL | not a browser-session cookie: that would silently turn a 30-day session into "until I close the window", experienced as random logouts; matching the TTL also stops the browser sending a cookie the server would only reject |
| `Secure` | **off** | `deployment.md` records HTTP only, no TLS anywhere |

The cookie's lifetime is a **hint**; `expires_at` in the row is the
**authority**. **Flip condition:** TLS termination anywhere in front of this
application makes `Secure` mandatory — the change surface is the one setter
(`deployment.md`'s TLS `_TBD:`).

## The stream routes — FEAT-009 and FEAT-010 in one router

**Realizes:** FEAT-008, FEAT-009, FEAT-010, UC-027, UC-028, UC-032, UC-035,
UC-036, UC-037, UC-078, UC-080, UC-083

One table, two views, one router (`routers/stream.py`). The merge in
`data-model.md` removed the surface the old two routers were named after: **the
`discussions` table is gone, so there is no discussion id to address**, and the
current zone has no id of its own either — it is the *set* of a session's
messages matching `related_to IS NULL AND settled_at IS NULL` (R11), and a set is
not addressable. Every zone operation is therefore addressed **through its
session**, and the route shape follows the two views exactly:

| Route | Does | Touches |
|---|---|---|
| `GET /api/sessions/{id}/entries` | the record above the ruler | `settled_entries`, `ORDER BY id` |
| `POST /api/sessions/{id}/entries` | file a pasted partner block, born settled (US-121) | one insert, `settled_at` set at insert |
| `GET /api/sessions/{id}/zone` | the live zone below the ruler | `current_zone`, `ORDER BY id` |
| `POST /api/sessions/{id}/zone/messages` | append one message; **no model call** | one insert |
| `POST /api/sessions/{id}/zone/compose` | append the roleplayer's message, then **stream** the assistant's reply | SSE; see below |
| `POST /api/sessions/{id}/settle` | settle the zone (R11, R12) | `services/settle.py` |
| `POST /api/sessions/{id}/reopen` | settle's exact inverse (R11) | `services/settle.py` |
| `PATCH /api/messages/{message_id}` | edit one message's text in place | one update |
| `POST /api/characters/{character_id}/sessions` | create a session under the character **and** seed its zone with the opening message, in one transaction (UC-080, US-117) | `services/sessions.py`; owned by `routers/sessions.py` |

The decisions behind that shape, each of which could have gone another way:

- **Settle and re-open take no target id.** R11 defines both structurally:
  settle takes *the last message in the zone* (US-126) and re-open applies to
  *the last settled row* — anything earlier has entries after it and is refused
  by definition (UC-037). The rejected alternative was
  `POST /api/entries/{message_id}/reopen`, matching where the control sits in the
  UI (`workspace-shell.md`). It was rejected because it lets a client name a row
  that is *not* the structural target, which turns an invariant the schema
  guarantees into a condition the server has to re-check and a client can get
  wrong. Session-addressed, the request cannot express an illegal target at all.
  The response returns the ids the operation moved, so the client can reconcile.
- **Two appends, not one route with a `reply: bool`.** UC-028/US-031 require text
  to reach the record with no model call at all, and UC-032/UC-034 require the
  streaming exchange. One route serving both would make the **response media
  type depend on a request field** — and the client picks its SSE reader or its
  JSON error renderer *before* the response arrives (`frontend-structure.md`).
  Two routes, two contracts, one media type each. That the composer's Send may
  map onto either is a UI decision, not a transport one; `docs/product/` does not
  describe the composer's send semantics beyond UC-028, so the split is recorded
  as a design inference rather than a read of a requirement.
- **A pasted partner block never passes through the zone** (US-121). It is born
  settled, and `POST /api/sessions/{id}/entries` is the only route that may
  create a settled row without settling. It accepts `kind='partner'` and
  **refuses every other kind**, which is R11's single exception enforced at the
  router boundary rather than trusted to a caller. It runs no `(( ))` parsing
  (R12) and returns JSON — there is nothing to stream for text the roleplayer
  did not compose.
- **`PATCH /api/messages/{message_id}` spans both views on purpose.** A settled
  row is editable forever (UC-078, US-110) and a zone message is editable in
  place including the assistant's (US-115); it is the same operation on the same
  column. A **buried** row is not editable (US-116), so the service refuses it
  with `message_not_editable`. The edit is also the write with the degraded
  embedding path — see the transaction rules at the end of this doc.
- **Starting a session by writing is one route and one transaction.** It is the
  only row in the table not addressed through a session, because when the request
  is made there is **no session to address**: UC-080 puts a composer on the
  character's page (`workspace-shell.md`), and the first message written there
  creates the session and becomes the opening message of the turn being drafted.
  **US-117.AC-1 makes creating the session and seeding its zone a single
  outcome**, so they are a single `with conn.begin():` in
  `services/sessions.py` — mint the session id, **resolve and capture
  `model_ref`** (R4: the model is captured at creation, not on first compose),
  insert the `sessions` row, insert the opening message as a current-zone row,
  commit together. The capture belongs inside this transaction like everything
  else in it; what creation does when **no model is enabled at all** is R4's open
  `_TBD:`, and this route is one of the two places that will have to answer it. The rejected
  alternative was leaving the client to call a create route and then
  `POST /api/sessions/{id}/zone/messages`: two round trips that can fail between,
  stranding an empty session under the character that the roleplayer never asked
  for and now has to archive by hand. A partial failure the *user* has to clean up
  is worse than a request that failed.
- **It is character-addressed, and it creates nothing settled.** The path is
  `/api/characters/{character_id}/sessions` because the character is the only
  entity that exists at request time. It is owned by `routers/sessions.py`
  (FEAT-008) rather than `characters.py` — routers here group by feature, not by
  path prefix, which is the same reason `stream.py` owns
  `PATCH /api/messages/{message_id}`. The response returns the new session, its
  `id` a decimal string per the JSON id boundary above, together with the seeded
  zone message, so the client can navigate and render without a second read
  (`frontend-structure.md`). The seeded message lands in the **current zone** and
  is never settled: UC-080's "opening message of that turn's discussion" *is* a
  zone row, so R11's "settle is the only door into the record" is untouched and
  this route is not a second exception beside the pasted partner block. The
  session is created with `setup_id` NULL — UC-080 names no setup, and R2 makes
  that the first-class case rather than a degraded one.
  `_TBD: docs/product/ does not state whether that first message should also draw
  an assistant reply. This route is JSON and makes no model call, matching the
  non-streaming append it is a variant of, and a compose can follow on the session
  route once the session exists. If UC-080 is meant to open the exchange as well,
  the response media type changes — so FEAT-008's plan must settle it rather than
  discover it._
- **The table has no discard operation, and that is now a decision rather than a
  gap.** It used to be recorded as a carried-forward product gap ("nothing says
  how a roleplayer walks away from the zone without settling"). UC-086, US-134
  and US-135 close it, and the answer leaves this table exactly as it is: an
  **empty** current zone has no rows, so abandoning it is a **frontend-only**
  clearing of the composer draft and the kind switch — no route, no backend
  surface (`workspace-shell.md`, R11). A zone that *holds* text is never
  discardable; it is settled instead, and US-135 guarantees settling never
  requires an assistant answer. **A discard route must not be added**: it would
  make raw `messages` writable from a third operation, weakening R11's
  two-operation invariant, in exchange for deleting rows that by definition do
  not exist.

### The streaming route

`POST /api/sessions/{id}/zone/compose` is the one streaming route. It returns a
`StreamingResponse(media_type="text/event-stream")` and sets **`X-Accel-Buffering:
no`** on that response (see `deployment.md` — the header is emitted by the
application, deliberately, rather than relying only on nginx's
`proxy_buffering off`). The request is a **POST with a JSON body**, which is why
the client is `fetch()` + `body.getReader()` rather than `EventSource`
(`overview.md`, `frontend-structure.md`).

The frame protocol and the tool loop are in `llm-and-streaming.md`. Two ordering
rules belong here because they are route-level:

1. **The roleplayer's message is committed before the stream opens** (R10). The
   handler inserts the zone row, commits, and only then begins generation — so
   `llm_unreachable` cannot lose typed text.
2. **A domain error mid-stream becomes an `error` frame, not an HTTP status.**
   The status was already sent. The frame carries the same `{code, message,
   detail}` shape as the JSON error body so the SPA has one error renderer.
3. **A client disconnect persists the partial assistant text and unwinds**
   (UC-085, US-132). The streaming generator detects the disconnect, writes
   whatever assistant text has accumulated as an **ordinary current-zone row**,
   and returns. It emits no terminal frame — there is nobody left to read one.

**The stop is a client disconnect and nothing else** (`llm-and-streaming.md`
owns the mechanism and its consequences). Three route-level facts follow, each
stated because the absent thing is what a reader will look for:

- **There is no stop route.** No `POST /api/sessions/{id}/stop`, and none may be
  added — the table above is complete.
- **There is no registry of in-flight work.** Nothing on application state maps a
  session, a user or a request to a running generator. The current zone has no id
  (R11), so there is nothing to key such a registry on, and adding one would put
  server state beside a request that may already be gone.
- **The partial-row write is the same write the success path performs**, not a
  special one: the assistant's row is a current-zone row either way, and the only
  difference is that no `done` frame reports its id. The client re-reads
  `GET /api/sessions/{id}/zone` to pick it up, which is
  `ui-conventions.md`'s never-optimistic re-load rule applying normally.

Because a stop, a network drop and a closed tab are the same event at this
layer, **the handler makes no attempt to distinguish them** — there is one
disconnect path, and a flaky connection gets the same partial-text preservation a
deliberate stop does.

## Settle and re-open — one transaction each, one module

**Realizes:** FEAT-010, UC-035, UC-036, UC-037, UC-081, UC-084

`services/settle.py` holds **both** operations and nothing else. R11 states that
raw `messages` is touched by exactly two operations; keeping those two in one
module turns that rule into a grep — any other module naming the `messages` table
is a review finding, and every other reader goes through a view.

**Settle**, entirely inside one `with conn.begin():`

1. Read the zone through `current_zone`; take the last row by id (US-126). An
   empty zone raises `zone_empty`. **That is the only precondition.** In
   particular there is **no requirement that the assistant has answered**: a zone
   holding only the roleplayer's own message settles that text as-is (US-135,
   UC-083 step 5 — "the last message in the current zone, **whoever wrote it**").
   Confirmed rather than newly stated, because the rule already read correctly;
   a check for an assistant row here would be a defect, and it is the kind of
   check that arrives disguised as validation.
2. Classify and strip through `services/parens.py` (R12): wholly parenthesised →
   `kind='decision'`, otherwise `kind='turn'` with any `(( ))` fragment removed
   from the head row's text.
3. `UPDATE messages SET related_to = <head id>` for every other zone row — bury
   the group.
4. `UPDATE messages SET settled_at, kind, text` on the head row.
5. Refresh `session_vec` (`search-and-retrieval.md`).

**Step 3 precedes step 4 and the order is load-bearing.** The burial predicate is
zone membership; once the head carries `settled_at` it is no longer in the zone,
and the set the burial is supposed to sweep no longer identifies itself. Two
UPDATEs and no INSERT — the settled text is the text already in the row
(`data-model.md`).

**Re-open** is the mirror, also one transaction: `related_to` back to NULL for the
group, `settled_at` and `kind` back to NULL on the head. It is gated on an **empty
current zone** (R11, US-128) and raises `zone_not_empty` otherwise; a head with no
buried group — a pasted partner block, which has nothing behind it — raises
`nothing_to_reopen`. That second refusal is **R11's own rule, not a guard this
module invented**: re-open applies only to a settled head that has a buried group,
because UC-037 re-opens a collapsed discussion and a partner block never had one. Ids never move, so a settle/re-open round trip leaves the
stream exactly as it started, which is what makes it safe as an undo.

Neither operation may commit partially: a buried group whose head was never
flagged is a session with no record and no zone. This is one of the reasons the
persistence layer is SQLAlchemy Core (below) — the transaction boundary is a
block in this module, not a flush the ORM schedules.

## The `(( ))` seam — one parser, server-side, at settle only

**Realizes:** FEAT-009, FEAT-010, UC-081, UC-084

`services/parens.py`. Two pure functions, no I/O, no `user_id`, no connection:

```
classify(text)        -> "decision" | "turn"
strip_fragments(text) -> str
```

It is called from **exactly one place: step 2 of settle.** R12 splits the
responsibility three ways — the server decides, the system prompt tells the model
how to read the convention, the client previews — and only the server's half is
code in this backend. The rule is cited, not restated.

The invariant this doc owns: **stored text is never re-parsed.** `PATCH
/api/messages/{message_id}` takes the new text literally and does **not** call
this module, on a settled row or a zone row; re-parsing a later edit would
silently delete prose a roleplayer deliberately parenthesised. Nor does
`POST /api/sessions/{id}/entries` call it — partner text gets no special
treatment (US-121). The pre-strip text is not preserved anywhere; there is no
revision table (`data-model.md`).

A pure module rather than a method on the settle service so the classification
and stripping cases are testable from the spec with no database at all, which is
what the pipeline's test-coder needs.

## Configuration — `pydantic-settings`

One `Settings` model in `app/config.py`, with **`RPHELPER_<FIELD>` validation
aliases**:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Field(default=Path("data"), validation_alias="RPHELPER_DATA_DIR")
    db_filename: str = Field(default="rphelper.sqlite", validation_alias="RPHELPER_DB_FILENAME")
    node_id: int = Field(default=0, validation_alias="RPHELPER_NODE_ID")
    session_cookie_name: str = Field(default="rphelper_session", validation_alias="RPHELPER_SESSION_COOKIE_NAME")
    session_ttl_hours: int = Field(default=720, validation_alias="RPHELPER_SESSION_TTL_HOURS")
    llm_request_timeout_seconds: float = Field(default=30.0, validation_alias="RPHELPER_LLM_REQUEST_TIMEOUT_SECONDS")  # plan 006

    # logging — sinks and their thresholds (deployment.md owns the posture)
    log_console_level: str  = Field(default="DEBUG",   validation_alias="RPHELPER_LOG_CONSOLE_LEVEL")
    log_file_level: str     = Field(default="WARNING", validation_alias="RPHELPER_LOG_FILE_LEVEL")
    log_file_path: Path     = Field(default=Path("data/logs/rphelper.log"), validation_alias="RPHELPER_LOG_FILE_PATH")
    log_file_rotation: str  = Field(default="10 MB",   validation_alias="RPHELPER_LOG_FILE_ROTATION")
    log_file_retention: int = Field(default=5,         validation_alias="RPHELPER_LOG_FILE_RETENTION")
    # ... one field per setting, each with an explicit RPHELPER_ alias

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- **Explicit `RPHELPER_` validation aliases** rather than an `env_prefix`, because
  an explicit alias per field makes the full environment contract greppable and
  keeps a field rename from silently renaming an operator-facing variable.
- **`lru_cache` singleton** so settings are parsed once at first use; routers
  depend on `get_settings` so tests override the cache rather than monkey-patching
  a module global.
- The env file resolves **relative to the backend working directory**, matching
  what `start.ps1` and the container both set.
- **Ports are not settings.** `8184` and `8193` are hardcoded literals in
  `start.ps1`, `vite.config.ts`, the Dockerfile and compose (`deployment.md`):
  they are topology, and making them configurable would create a way for the Vite
  proxy target and the uvicorn bind to disagree.
- **`node_id` is a setting** and is the one field the id generator reads. It is
  configurable so two instances can be given different node ids. **Its earlier
  justification — that FEAT-018 import preserves ids and therefore needs
  non-colliding node ids — is superseded**: US-136.AC-2 makes import mint fresh
  ids and remap the payload's internal references (`data-model.md`), so import
  uses this same generator and needs no cross-instance guarantee at all.
- **`session_ttl_hours`** (default 720) is read once per session, when its
  `expires_at` is written, and the expiry is never moved afterwards — no sliding
  expiry, no refresh route ("Session lifetime" above has the reason and the flip
  condition). **`session_cookie_name`** is the only source of the cookie's name.
- **The five `log_*` fields** are the only configuration the logging module
  reads. `log_file_path` defaults under `data/` because that is the one writable
  volume in prod; `deployment.md` owns that reasoning and the redaction rule.

### The logging call site — once, in the app factory

**Realizes:** FEAT-019

`app/logging.py` exposes one function, `configure_logging(settings)`, and it is
called **exactly once, from `main.py`'s app factory, before any router is
registered** — early enough that a failure during registration is already
captured by both sinks. It does three things and nothing else:

1. removes loguru's default stderr handler and adds the two configured sinks
   (console at `log_console_level`; the rotating file at `log_file_level`, with
   `rotation`, `retention` and **`diagnose=False`**);
2. creates `log_file_path`'s parent directory if it does not exist;
3. installs the **`InterceptHandler`** as the stdlib `logging` root handler and
   clears `uvicorn`, `uvicorn.access`, `uvicorn.error` and `sqlalchemy`'s own
   handlers so their records propagate into it.

Step 3 is the load-bearing one and the one that fails silently —
`deployment.md` records why, and the flip condition if the bridge proves
fragile. No other module in the backend adds, removes or reconfigures a sink;
call sites use `loguru.logger` directly and pass **ids, codes and counts, never
text** (`deployment.md`'s redaction rule, which binds every log line in this
codebase at every level).

## The `"$ENV_VAR"` secret-pointer pattern

**Realizes:** FEAT-004, FEAT-018, UC-010, UC-061

An LLM server's credential is **never stored in the database**. The
`llm_servers.api_key_ref` column holds a *pointer*: the literal string
`"$OPENAI_API_KEY"`, resolved from the process environment at call time.

```python
def resolve_secret(ref: str | None) -> str | None:
    """'$NAME' -> os.environ['NAME']; None -> None; anything else -> SecretRefError."""
```

- A value that does not start with `$` is **rejected on write**, so a pasted raw
  key cannot be persisted by accident. The admin UI says what the field expects.
  **Where and how** (plan 006): an annotated pydantic field type in
  **`app/models/secret_ref.py`**, answered by FastAPI's own **422** and adding no
  domain error code. `resolve_secret` is unchanged and handles read-time
  resolution alone.
- **The empty string is a legal value** meaning "no pointer" on create and "clear
  the stored pointer" on update (`admin-surfaces.md`'s round-trip rule).
- Resolution happens **at call time**, not at registration and not at startup, so
  rotating a key is an environment change plus a restart — no database write, no
  re-registration.
- A missing environment variable is a **typed error** (`secret_ref_missing`), not
  a `None` that turns into an unauthenticated request against the provider.
- **It has an administrator-facing call site since plan 006**: the
  test-connection route lets it propagate as a **500** and records nothing on the
  row. Why 500 is right, and when it would stop being right, is "The 500 posture"
  under the error model below.

Why this is right for RPHelper rather than merely inherited from BookWriter:
FEAT-018/UC-061 requires a whole-database export an administrator may move
between instances, and FEAT-019 makes that export deliberately opaque. A database
holding credentials would turn every export into a secret-bearing artifact and
every drift report into something needing redaction. With pointers, the export
moves configuration and the environment supplies credentials.

## The error model

**Realizes:** FEAT-001, FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-009,
FEAT-010, FEAT-011, FEAT-013, UC-003, UC-006..UC-015, UC-032, UC-037, UC-039,
UC-087, US-006.AC-3, US-018.AC-6, US-018.AC-7, US-140

Domain failures in RPHelper are not incidental — several are *product behaviour*.
"Your session's model was disabled" (UC-012) and "translation failed, showing the
original" (UC-039) are outcomes the SPA must render specifically, so they cannot
arrive as an opaque 500 or a prose string.

One base class, one wire shape, one handler:

```python
class DomainError(Exception):
    code: str          # stable machine-readable identifier
    http_status: int
    detail: dict       # structured, never free prose the UI has to parse
```

**`code` and `http_status` are class attributes each concrete subclass sets**;
the base declares them and gives them no value. The status a code answers with is
**decided by the feature that introduces the code**, in the subclass it declares.
`detail` (and the optional `message`) are per instance, `detail` defaulting to
empty.

**The table below carries no status column, by design rather than by omission.**
A code's status is a property of its subclass, decided where the code is born, so
the error table records *what* a code means and leaves *how it is answered* to the
per-code status record further down. Without a recorded rule, twenty codes would
have their statuses decided twenty separate times with nothing tying them together.

**Handler registration** (decided in plan 001). `errors.py` exposes one
registration entry point, `register_exception_handlers(app)`, which installs the
one handler for the `DomainError` base class on the application; `main.py`'s app
factory calls it. One registration on the base covers every subclass, so a feature
adding a code adds a subclass and touches no registration. The handler reads the
status off the instance's `http_status` and renders the wire body below. Recorded
because the "one handler" rule otherwise names no call site and would be
re-inferred — possibly differently — by the next feature that adds a code.

Wire shape for every non-2xx the SPA is expected to handle:

```json
{ "error": { "code": "model_not_enabled", "message": "...", "detail": { ... } } }
```

The named errors the design requires:

| `code` | Raised when | `detail` carries | Realizes |
|---|---|---|---|
| `model_not_enabled` | Use-time validation of a resolved model reference fails (R4) | the model reference — **the server id as a decimal string and the model name** — and **which level set it**, constrained to `character` or `session`, **never `user`**: there is no user-level model default (UC-050, R1's correction) | FEAT-004, UC-012 |
| `no_embedding_model` | An embedding is attempted with no designated embedding model, or the designation is gone, or the designated model is not also enabled (R4) | nothing user-scoped | FEAT-004, UC-013 |
| `secret_ref_missing` | `"$ENV_VAR"` names an absent variable | the variable name | FEAT-004 |
| `username_taken` | An account is created with a username that already exists | nothing | FEAT-003, UC-006 |
| `user_not_found` | An admin route addresses an account id that does not exist | nothing | FEAT-003, UC-007, UC-008, UC-009, UC-087 |
| `self_role_change_refused` | A role change whose target is the acting administrator | nothing | FEAT-003, UC-087, US-140.AC-2 |
| `llm_server_not_found` | An admin LLM route addresses a server id that does not exist | nothing | FEAT-004, UC-010..UC-013 |
| `unknown_table` | A drift-page apply route names a table the registry does not declare | the table name | FEAT-005, UC-015 |
| `schema_apply_failed` | A `Create` or a `Sync` could not be applied — a driver error, a failed cast, or a `PRAGMA foreign_key_check` violation | the table name and the operation (`create` \| `sync`); **never the driver's message** (below) | FEAT-005, UC-015, US-018.AC-6, US-018.AC-7 |
| `llm_unreachable` | Provider call fails or times out | provider-side message, no request body | FEAT-010, UC-032 |
| `tool_failed` | A tool invocation fails — **not surfaced as a stream error** (R9) | tool name | FEAT-014, FEAT-015, FEAT-016 |
| `translation_failed` | UC-039's exception flow; nothing is cached | the message id, as a string | FEAT-011 |
| `zone_empty` | Settle is attempted with nothing in the current zone (R11) | nothing | FEAT-010, UC-083 |
| `zone_not_empty` | Re-open is attempted while the session's current zone is not empty (R11, US-128) | nothing | FEAT-010, UC-037 |
| `nothing_to_reopen` | Re-open is attempted where the last settled row has no buried group — a pasted partner block (US-121) | nothing | FEAT-010, UC-037 |
| `message_not_editable` | An edit targets a **buried** row (US-116) | nothing | FEAT-010, UC-036 |
| `already_configured` | A bootstrap route is reached on a configured instance (UC-003) | nothing | FEAT-001 |
| `invalid_credentials` | A login attempt fails for **any** reason — unknown username, wrong password, or a disabled account | nothing | FEAT-002, US-006.AC-3 |
| `not_authenticated` | A guarded route is reached with no session cookie, or one that does not resolve to a live session | nothing | FEAT-002 |
| `insufficient_role` | An authenticated, enabled caller's role is below the required rung | nothing — **it names neither the caller's role nor the required one** | FEAT-002 |

**`account_disabled` is struck** (plan 004). Nothing raises it: a correct password
on a disabled account receives the same `invalid_credentials` refusal as a wrong
password — same code, status and message (US-006.AC-3) — and the login screen
renders one message for all three causes. The row is struck because it has **no
caller**, not because the concept is wrong; FEAT-003's planner **may reintroduce
it** if an administrator-facing surface needs a distinguishable code.

**`already_configured` carries a default human-readable `message`** (plan 003).
Raised with no arguments — as `require_unconfigured` raises it — it renders a
non-empty `message`, so the wire body matches the shape above, where `message`
is a string. **The default lives on the subclass**: the base class and its
handler have no class-level default message, because adding one there would
change what every other error renders. The base stores a message exactly as
given, which is how plan 003's first build shipped `"message": null` on its 409.
Whether other named errors adopt the same subclass-default pattern is decided per
code, by the feature that introduces it.

**`discussion_not_resumable` is renamed to `zone_not_empty`, and the rename is
not cosmetic.** The old code named a table that no longer exists and a condition
that has changed: it fired when "an entry follows the answer", which was a
property of the settled record. The condition now is that **the session's current
zone is not empty** (US-128, R11) — a property of the zone, checked against the
`current_zone` view. Same product guarantee, different predicate, so the same
name would have been actively misleading. Its two sibling failures,
`zone_empty` and `nothing_to_reopen`, exist because settle and re-open are
distinct operations that fail for distinct reasons and the SPA renders them
differently: nothing to settle, not yet re-openable, nothing behind this entry.

Three rules about `detail` that are privacy or correctness rules, not formatting
preferences:

- **`detail` never contains another user's data**, and never a count derived from
  it (R5). `model_not_enabled` names the model and the level, never how many
  sessions are affected.
- **`detail` never contains memo body text for a note where `is_enabled` is
  false** — R3's "no path" includes error payloads.
- **Any id in `detail` is a decimal string**, per the JSON id boundary above.

`model_not_enabled` carrying *which level set the reference* is the one place the
error model does real product work: UC-012 says the roleplayer resolves the
situation "by choosing another model through FEAT-013's chain", and they can only
do that if they are told whether the dead reference came from the character or
from this session. (It used to say "their account default, the character, or this
session" — there is **no account default for a model**; see R1's correction.)

### The per-code status record

One row per code, added by the feature that introduces the code's subclass, with
the reason for the status beside it. A code not listed here has not been
introduced yet.

| `code` | HTTP status | Reason | Introduced by |
|---|---|---|---|
| `secret_ref_missing` | **500** | the **500 posture** below — the instance's environment is misconfigured, and nothing about the request is malformed. Reachable from an administrator's test-connection action since plan 006; kept at 500 by user decision at the finalization of plans 001..007 (H1) | plan 001 |
| `already_configured` | **409** | the request is well formed and no identity is being judged — the instance's state conflicts with the operation. **403 rejected:** there is no caller identity to authorize on an instance that may not even be configured. **404 rejected:** hiding the route would make UC-003's "directs them to sign in instead" undiagnosable | plan 003 |
| `invalid_credentials` | **400** | **not 401, deliberately.** The shared API client performs a document navigation to `/login` on **any** 401 and then still throws (`frontend-structure.md`), so a 401 from the login route would reload the login page and destroy the message US-005.AC-2 requires the user to see. **401 plus a per-call opt-out rejected:** it widens a shared module's contract for one call site. **403 rejected:** nothing has been authenticated, so there is no identity to refuse an action to. A reader "correcting" this to 401 breaks the login screen in a way that presents as "the form does nothing" | plan 004 |
| `not_authenticated` | **401** | the condition the client's 401 navigation exists for | plan 004 |
| `insufficient_role` | **403** | a genuine authorization failure for an identified caller; the client renders a 403 rather than redirecting | plan 004 |
| `username_taken` | **409** | a conflict with existing state for a caller who is authenticated and authorized; **403 rejected** because it is already spoken for by `insufficient_role` | plan 005 |
| `self_role_change_refused` | **409** | same reasoning as `username_taken`: an authorized caller, a request that conflicts with a rule; **not 403** | plan 005 |
| `user_not_found` | **404** | the path's account id addresses no row | plan 005 |
| `llm_server_not_found` | **404** | the sibling of `user_not_found`: the path's server id addresses no row | plan 006 |
| `llm_unreachable` | **502** | the failure is the upstream provider's, and there is no useful partial answer to give (the available-models route, "The connection probe" below) | plan 006 (status left open by this table until then) |
| `no_embedding_model` | **409** | assigned by plan 006, which introduced the first raising path; the request is well formed and the registry's state conflicts with it — the same shape as `already_configured` (this doc's gloss; the plan records the status, not a separate reason) | plan 006 |
| `model_not_enabled` | **409** | as `no_embedding_model` | plan 006 |
| `unknown_table` | **404** | the path's table name addresses no registry entry | plan 007 |
| `schema_apply_failed` | **500** | the **500 posture** below — the instance failed to do what it offered | plan 007 |

#### The 500 posture — `secret_ref_missing` and `schema_apply_failed`

**Decided by the user at the finalization of plans 001..007 (H1): both keep 500,
and they are one deliberate posture, not two accidents.** Plans 006 and 007 each
flagged their code as worth a second look, because each is now reachable from a
routine administrator action — a test connection, a Sync — and so can put a 500
in the logs. The answer is the same for both:

- **Nothing about the request is malformed.** A 4xx says "the caller asked
  wrongly"; here the caller asked correctly. `schema_apply_failed` means the
  instance **failed to do what it offered** (a cast failed, a foreign-key check
  failed, the driver refused). `secret_ref_missing` means the instance's
  **environment is misconfigured** — fixable only by changing the environment and
  restarting, never by a different request. **409 and 422 were rejected** for
  that reason.
- **Neither is a field-level message.** The admin surfaces render both as a
  failure panel, not as a correctable input error (`admin-surfaces.md`'s LLM
  Servers and Database pages).
- **The driver's message never reaches `detail` or a log line**
  (`schema_apply_failed`): a SQLite error text can embed a column **value**, which
  would put user content into an administrator-facing payload (R5,
  `deployment.md`'s redaction rule). `detail` carries the table name and the
  operation only.
- **The test-connection route lets `secret_ref_missing` propagate and records
  nothing on the row** (plan 006): the failure is a configuration fault of the
  instance, not a property of the connection, so it must not be written into
  `last_test_*` as though the server had answered.

**Flip condition:** an admin surface needs to render either case as an
**actionable, field-level message** rather than a failure panel. That code then
moves to a 4xx. No code changed with this decision.

## `/api/health`

**Realizes:** FEAT-001, FEAT-005

`GET /api/health`, unauthenticated, is the readiness probe. It reports:

```json
{ "status": "ok" | "unconfigured" | "degraded",
  "configured": true|false,
  "schema": "ok" | "drift" | "missing" }
```

- **`configured`** is FEAT-001's signal: a database with at least one
  administrator exists. The bootstrap entry uses it to decide whether to offer
  bootstrap at all; UC-003's refusal is the server-side enforcement of the same
  fact.
- **`schema`** is a coarse roll-up of FEAT-005's drift check (the detailed
  per-table report is admin-only, `admin_db.py`). It is safe unauthenticated
  because it names no table contents and no user.
- It is also the container healthcheck target (`deployment.md`), which matters
  because `supervisord` has no wait-for ordering: nginx can accept connections
  before uvicorn is listening, so the probe has to come from the app.

The endpoint deliberately **touches the database** rather than returning a static
`{"status":"ok"}`. A health check that cannot fail tells an operator nothing, and
FEAT-001's whole problem is an instance that is running but not usable.

**Since plan 007 the probe runs the drift check's PRAGMA walk**, not one
`sqlite_master` read, on an endpoint that is also the container healthcheck
target. Accepted over a handful of tables on a WAL file. **Flip condition:** if
the registry grows to where the walk shows against the healthcheck interval, the
roll-up narrows back to presence and the drift branch moves behind the admin
route. **Caching the probe is explicitly rejected** — a cached health check cannot
fail, which is what this section says the endpoint exists not to be. The registry
still reaches `probe_health` as a **parameter**.

### Behaviour, roll-up and status codes

- **Against an empty registry, `schema` is `"ok"`, and that is correct rather
  than a stub.** The probe answers "is every declared table present?"; with
  nothing declared the answer is yes. This is the state the system is in for the
  whole of stage 001, which is why it is stated.
- **`schema` precedence: `"missing"` > `"drift"` > `"ok"`.** Any declared table
  absent gives `"missing"`; otherwise any present table whose shape diverges from
  its declaration gives `"drift"`; otherwise `"ok"`. `"drift"` is produced by
  FEAT-005's drift check (plan 007); plan 001 declared the value and produced only
  `"missing"` / `"ok"`. **Missing outranks drift** because a table that does not
  exist fails every query against it, and the admin page's badge colours follow
  the same order (`admin-surfaces.md`). The roll-up is **one word naming no
  table**, which is what keeps the endpoint safe unauthenticated.
- **`status` roll-up:** a non-`"ok"` `schema` gives `"degraded"`; otherwise
  `configured` false gives `"unconfigured"`; otherwise `"ok"`.
- **All three `status` values answer HTTP 200** (decided in plan 001). The body
  *is* the answer, and every consumer — the bootstrap entry, the container
  healthcheck, an operator — must be able to read it; returning `"degraded"` as a
  503 would make the SPA discard the very body that explains the condition. **A
  probe that cannot read the database at all is a 500** — that is the case where
  there is no body worth reading.
- **Later features widen this function; they do not rewrite it.** `configured` is
  sharpened by FEAT-001's bootstrap (plan 003) and `"drift"` is filled in by
  FEAT-005 (plan 007); the response shape above is unchanged by either.

### A genuinely pre-bootstrap instance reads as `"degraded"` — and that is correct

Once `users` is in the registry (plan 003), an instance with no schema at all
answers:

```json
{ "status": "degraded", "configured": false, "schema": "missing" }
```

because a declared table really is absent and the roll-up gives a non-`"ok"`
`schema` precedence over `configured`. "Degraded" on a brand-new instance reads
like a fault and will be reported as one; it is not. Two consequences for
clients:

- **The bootstrap entry branches on `configured` alone and never on `status`**
  (`frontend-structure.md`). `configured` is FEAT-001's signal; `status` is an
  operator's roll-up.
- **`status: "unconfigured"` is the narrower case** of a database whose tables
  exist with no administrator row in them.

**The endpoint answers HTTP 200 whatever the roll-up says**, and the compose
healthcheck depends on exactly that: it asserts the status code and never the
body (`deployment.md`). The two facts are read together — a body-inspecting
healthcheck would make a fresh instance permanently unhealthy.

## `GET /api/me`

**Realizes:** FEAT-002, FEAT-003, FEAT-019, FEAT-020, UC-071

Owned by `auth.py`. Returns the **caller's own identity** and nothing else:

```json
{ "id": "7250...", "username": "...", "role": "roleplayer" | "admin" }
```

(`id` is a string — the JSON id boundary applies here as everywhere.)

It requires a live session and answers **401** when there is none, or when the
session's account no longer resolves — deleted, or disabled (FEAT-003). It
carries no counts, no other accounts and no content. It is a read path scoped to
`require_user`'s `user_id`, which is the whole of its scope.

Three consumers, and the first is why it exists:

- **The `admin` entry awaits it before mounting** (`admin-surfaces.md`). RPHelper
  cannot decode a role client-side — the session is an HttpOnly cookie — and
  FEAT-003's "disabling an account ends that user's sessions" requires a
  server-side check anyway, because a stateless token cannot be revoked. The
  admin gate is one round-trip to this route, and the entry renders nothing until
  it answers.
- **The `app` entry's user menu** (UC-071, `workspace-shell.md`). The menu offers
  settings and log out to everyone (US-091, US-092) and an admin entry point
  **only to ACT-001** (US-093) — `role` from this route is what decides whether
  that item is rendered at all, and US-093.AC-2 requires it to be *absent* rather
  than disabled. The menu also shows the username. Hiding the item is UX; the
  boundary is still `require_role` on the admin routers.
- The sign-out affordance in the same menu (US-091).

The 401-on-disabled behaviour is load-bearing rather than incidental: it is the
point at which FEAT-003's session termination becomes observable to a client that
is already loaded. Since FEAT-002 it is mechanically true rather than promised:
the route sits behind `require_user`, whose resolution requires an enabled
account ("What `require_user` resolves", above), and answers with
`not_authenticated`.

## The connection probe — one primitive, two routes

**Realizes:** FEAT-004, UC-011, UC-012, UC-013

There is **one** piece of code that talks to an OpenAI-compatible server to find
out whether it answers and what it offers — the probe primitive, in
`services/llm_registry.py`. It resolves the server's `"$ENV_VAR"` pointer, issues
the request, and returns a typed outcome or raises a typed error
(`secret_ref_missing`, `llm_unreachable`).

That one primitive is exposed as **two distinct routes** in `admin_llm.py`:

| Route | Purpose | Result |
|---|---|---|
| list available models — `GET …/{server_id}/available-models` | populates the models and embedding modals (UC-012, UC-013) | the model names the server offers |
| **test connection** — `POST …/{server_id}/test` | UC-011's own capability | a typed connection-test result |

**The second route is a deliberate deviation from the sibling project**, which
tests a connection by reusing the model listing. Reason: FEAT-004 treats testing
a connection as its **own** capability, and overloading the model-listing call
conflates two questions — "can I reach and authenticate against this server" and
"what can it run". A UI that must open a model picker to learn that a base URL is
wrong is answering the first question as a side effect of the second. Reusing the
*primitive* while splitting the *route* keeps one implementation and two honest
contracts.

The test route writes `llm_servers.last_test_at` / `last_test_ok` /
`last_test_error` (`data-model.md`), and per UC-011 a failed test **never** blocks
or removes a registration. Its result is a **typed value**; the four-value set and
its ok mapping are in `admin-surfaces.md`.

### As built (plan 006) — two routes, opposite error postures

- **The primitive writes nothing.** It resolves the pointer, builds a client
  through an **injectable factory**, and returns a typed outcome.
- **The test route answers 200 even for a failing outcome** and writes the three
  `last_test_*` columns — the test succeeded; the connection did not.
- **The available-models route writes nothing and answers 502
  `llm_unreachable`** for an unreachable or auth-failed server — there is no
  useful partial answer to "what can it run".
- Consequence: **opening a models modal cannot overwrite the administrator's last
  deliberate test result.**
- The two opposite postures are the pair a later reader would "harmonise"; do
  not. `secret_ref_missing` is the exception to "200 even for a failing outcome":
  it propagates as a 500 and records nothing ("The 500 posture" above).

### The first async code in the backend, and what it costs

Plan 006 moved **`httpx` from the dev dependency group into the runtime
dependencies** — the first outbound-HTTP code in `app/` — and the client is
**`httpx.AsyncClient`**, because FEAT-009/010's streaming goes through the same
module and a sync client would have to be rewritten.

Consequence: the three registry operations that reach the network are
`async def`, and so are their three routes, while the SQLAlchemy `Connection`
they hold stays **sync** — so their small single-row reads and writes block the
event loop briefly. The persistence sections below are written on the assumption
that everything is sync; this is the first exception.

**Flip condition:** if a request path ever needs a long or multi-statement
transaction around an awaited call, the mix has to be resolved rather than
extended — either by moving the database work off the loop or by adopting an
async driver.

## Database access

One SQLite connection factory in `db/engine.py`, which on every connection:

- sets `PRAGMA foreign_keys = ON`,
- sets `PRAGMA journal_mode = WAL` — readers do not block the single writer,
  which matters because an SSE compose exchange holds a request open while other
  reads happen,
- loads the `sqlite-vec` extension, so `vec0` tables and the KNN operators are
  available on every connection rather than only where someone remembered,
- and runs the pysqlite driver with **transactional DDL** (below).

### Transactional DDL — the driver never opens or commits on its own

Decided in plan 003. `db/engine.py` turns the pysqlite driver's own implicit
transaction handling **off**, so the driver never opens or commits a transaction
by itself, and SQLAlchemy's `begin` sends the real `BEGIN`. This is SQLAlchemy's
documented "pysqlite transactional DDL" configuration. So a
`with conn.begin():` block covers **every** statement inside it, `CREATE TABLE`
included, and savepoints behave.

**Why.** Under the driver's default (legacy) transaction control, SQLAlchemy's
`begin()` sends no `BEGIN`, and the driver opens a transaction only right before
DML, so DDL autocommits. FEAT-001's first build found this: a failed
first-administrator insert rolled back the row and **left the tables** — exactly
the half-bootstrapped state the bootstrap's single transaction promises cannot
exist. Every "these writes commit together or not at all" claim in this doc —
reason 1 of the Core decision below — is only true with this setting, and
settle, memo-plus-embedding, account-disable and FEAT-005's DDL all rely on it.
It is an **engine-wide property, not a bootstrap special case**, so that the
process has one transaction semantics.

Constraints that come with it:

- **The per-connection PRAGMAs still run outside any transaction.**
  `journal_mode = WAL` cannot be entered inside one, and `foreign_keys` is a
  no-op inside one — so a driver mode that keeps a transaction open at all times
  is excluded, and the `connect` listener runs in autocommit.
- **`get_connection` still opens no transaction** (below).
- **An autobegun read now holds a real deferred `BEGIN`** until the caller's
  rollback or commit, or the pool's reset-on-return. Consequence: **a caller that
  runs a read and then `begin()` on the same connection must end the read's
  transaction first**, or `begin()` raises. Plan 003's `is_configured` ends its
  own implicit read for exactly this reason (the bootstrap guard and handler share
  one request-scoped connection); `/api/health`'s probe does not, which is safe
  only because no live path runs it and then `begin()` on the same connection.

**Flip condition:** if the project moves off the stdlib `sqlite3` driver, or a
later SQLAlchemy/Python release makes transactional DDL the default, re-check
this setting and drop it if it has become redundant. The DDL-rollback test added
with FEAT-001 (`backend/tests/test_db_engine.py`) is the check.

### The PRAGMA and WAL lifecycle — one listener, every connection

All three are applied by a **single SQLAlchemy `connect` event listener on the
engine**, which runs on every new connection — extension load, then
`foreign_keys`, then `journal_mode` — and **none of it is applied per
transaction**. One mechanism, no first-open special case:

- `PRAGMA foreign_keys = ON` genuinely is per-connection state and must be re-set
  on every connection, so the listener is required for it regardless. **One code
  path suspends it** — a FEAT-005 Sync rebuild, outside its transaction, restored
  on both paths ("Schema evolution", below).
- `PRAGMA journal_mode = WAL` is a **persistent, file-level** property. Re-asserting
  it on a connection that already sees WAL is a cheap idempotent no-op.

The rejected alternative was setting WAL once, at first open. That is a second
mechanism with its own ordering question ("first open" of what, by whom, before
which connection?) for a statement that costs nothing when it is a no-op.

### Pooling, threading and the engine cache

**One `Engine` per resolved database path**, cached in `db/engine.py`, using the
pysqlite dialect's **default pool** for a file database with the DBAPI
**same-thread assertion disabled** (`check_same_thread=False`), plus a disposal
entry point that disposes and forgets every cached engine, for teardown.

- **Why the same-thread assertion is off.** uvicorn hands a pooled connection to
  whichever worker thread runs the request. The pool already guarantees a
  connection is never used by two threads at once, so the assertion forbids the
  normal case while protecting against nothing.
- **Why the cache is keyed on the path** rather than being a module singleton:
  it is what lets per-test databases coexist in one process (the test conventions
  in `quick-reference.md`).

### The `get_connection` dependency

**`get_connection`, declared in `db/engine.py`, is the single, request-scoped way
a router obtains a Core `Connection`.** It is a FastAPI generator dependency: it
acquires a connection from the engine, yields it for the life of the request and
closes it afterwards. **It opens no transaction** — transaction boundaries stay
`with conn.begin():` blocks at the service's own level (below). Naming the
dependency is what keeps connection lifetime out of handler code; the doc
previously described a connection factory with no call-site mechanism.

### A failed `sqlite-vec` load fails loudly

A connection on which the extension cannot be loaded **raises a dedicated
operational exception** (`ExtensionLoadError`) rather than being handed out
without the extension. Like the id generator's backwards-clock exception, it is
**not** a `DomainError` subclass: it is an environment fault, not something the
SPA renders. Reason: the extension is a hard requirement from stage `004` onward,
and a silently missing extension surfaces much later as an inexplicable query
error, in a feature that did nothing wrong.

**The version is pinned in `backend/pyproject.toml`: `sqlite-vec==0.1.9`.** The
docs named no version, so the pin is a decision rather than a transcription,
taken because the extension's availability is a hard runtime requirement.

### Persistence access — SQLAlchemy **Core**, not the ORM

Decided. Data access goes through **SQLAlchemy Core** — `MetaData`, `Table`,
`select()`/`insert()`/`update()`, explicit `Connection` and `begin()`. The
**declarative ORM is not used**: no `DeclarativeBase`, no mapped classes, no
`Session`, no identity map, no lazy loading.

Three reasons, in the order they decided it:

1. **Explicit transaction scoping.** The R-rules require transactions the code
   can see: settle's two UPDATEs plus the `session_vec` refresh commit together
   or not at all (above), a memo write and its embedding write are one
   transaction (`search-and-retrieval.md`), and disabling an account flips
   `users.is_enabled` **and** revokes its `auth_sessions` rows atomically
   (FEAT-003). Core makes the boundary a `with conn.begin():` block at the
   service's own level. The ORM's unit-of-work flushes when it decides to, which
   is exactly the wrong property for an invariant stated as "these writes commit
   together or not at all". The block covers DDL too only because of the
   engine's transactional-DDL setting ("Transactional DDL", above).
2. **A `text()` escape hatch for the queries no ORM expresses.** `vec0 MATCH`
   with a bound query vector and `ORDER BY distance`, and FTS5 `MATCH` with
   `bm25()`, are SQLite-extension syntax with no expression-language equivalent,
   and `search-and-retrieval.md`'s relational-CTE-feeding-two-arms shape has to
   be written as SQL. Core lets that be `text()` against the same connection and
   inside the same transaction as everything around it, instead of an ORM session
   plus a raw-connection side channel with two transaction stories.
3. **FEAT-005 needs a registry it can introspect, not mapped classes.** UC-014
   asks for the *current structural truth per table*, answered by `PRAGMA
   table_info` / `index_list` against a declaration. A Core `MetaData` with
   `Table` objects **is** that declaration — `db/schema.py` stays the single
   introspectable source of truth and `db/drift.py` walks it directly.

**The registry's concrete shape: one module-level
`metadata = MetaData()` in `db/schema.py`, with every table declared as a
`Table(...)` literal in that same file.** (Closed by plan 001.) No per-feature table modules, no
import-side-effect registration, no `build_registry()` callable; FEAT-005's drift
check walks `metadata.tables`. Reason: the root `CLAUDE.md` already makes
`db/schema.py` *the* source of truth, a single file has no import-order hazard,
and nothing can be silently absent from the drift report because the module that
declared it was never imported. Plan 001 shipped the file with the `MetaData` and
zero tables; each later feature adds its `Table` literals there.

The registry in `db/schema.py` remains authoritative for both the creation path
and the drift report, and all SQL stays in `services`/`db` so R5's query-level
scoping is auditable in one layer. The two SQL views (`data-model.md`) are
declared there too, and are what every reader but `services/settle.py` selects
from.

### Schema evolution — the registry is the truth, the administrator applies

**Decided.** The earlier `_TBD:` here — migration files versus registry-only
create-if-missing — is **closed by a user decision**, taken from the sibling
project BookWriter, which carries a "DB shape check" administrative page where
the administrator sees the divergence between the declared model and the live
database and applies the shape change. RPHelper copies that.

Five facts, each stated because it is the one a reader would otherwise assume
wrongly:

1. **`db/schema.py` remains the single source of truth.** The argument for a
   registry over a migration ledger is `data-model.md`'s and is unchanged:
   UC-014 asks for the *current* structural truth per table, and a migration
   history cannot answer it — a database that skipped a migration and one that
   was hand-edited look identical to a ledger and different to an introspection
   check.
2. **There is no migration history.** No `versions/` directory, no revision
   chain, no version table, and **no automatic upgrade at startup** —
   `main.py`'s lifespan runs no DDL. Each of these is written as an explicit
   negative because the library named in (4) normally implies all four, and a
   reader who finds it in the dependency list will otherwise assume them.
3. **The drift page's `Sync` action is the shape-change mechanism**
   (`admin-surfaces.md`). The administrator reads the per-table divergence and
   applies it. This is a deliberate human-in-the-loop gate: a DDL change to a
   table holding the roleplayer's own material is not something to apply
   silently at boot. `Create` — UC-015's "creating missing tables" — is its
   sibling action on the same page.
4. **Alembic is adopted as the DDL *executor* only, not as a migration
   framework.** The concrete reason is SQLite: it cannot drop or retype a column
   in place, so applying a shape change means the create-copy-drop-rename table
   rebuild, and Alembic's **batch operations** are the well-tested
   implementation of that dance. That is the whole of the reason, recorded this
   narrowly on purpose — "we use Alembic" without it is how a `versions/`
   directory arrives later.
   **As built (plan 007):** `alembic` is a **runtime** dependency in
   `backend/pyproject.toml` — before, it was named here and in the stack table
   but was not a dependency at all. Fact 2's four negatives are now **assertions a
   verifier checks**, not intentions: no `versions/` directory, no revision chain,
   no version table, no upgrade at startup — `main.py`'s lifespan still runs no
   DDL, and FEAT-001's "`sqlite_master` is empty after startup" assertion still
   passes. The API surface actually used is narrow:
   `alembic.migration.MigrationContext` plus `alembic.operations.Operations`
   around the request's own `Connection`, and `batch_alter_table` in **recreate
   mode**. Nothing from `alembic.config`, `ScriptDirectory`,
   `EnvironmentContext` or `command.*` is imported.
5. **First-run creation is `create_all`, and it is request-time** (plan 003).
   FEAT-001's bootstrap applies the registry with SQLAlchemy's own
   create-if-missing creation against the single `MetaData` in `db/schema.py`,
   bound to the request's connection and **inside the same transaction as the
   first administrator's insert** (and, since plan 004, the operator's first
   session), so no half-bootstrapped instance is reachable. This is **neither DDL
   at startup nor FEAT-005's admin-triggered Sync**: it is a one-time,
   operator-triggered operation on an instance that has no schema at all, it uses
   no Alembic and no `db/sync.py`, and fact 2's "no DDL at startup" is untouched.
   "Inside the same transaction" is true only because of the engine's
   transactional-DDL setting (Database access, above).

**Where the executor lives: `db/sync.py`**, beside `db/schema.py` and
`db/drift.py`. It takes **the registry and a table name**, resolves the `Table`
itself, raises `unknown_table` when the registry does not declare it, calls
`db/drift.py` for the report row it needs, and emits the batch operations that
close the gap. It holds no state of its own and is called only from
`routers/admin_db.py`'s Create and Sync routes. Diagnosis stays in `db/drift.py`
and remediation lives in `db/sync.py`, so the code path that only reports cannot
write: **`db/sync.py` may import `db/drift.py`, and the reverse import is a
defect.**

**Correction (plan 007).** This paragraph used to say the executor takes "a
drift-report row plus the registry's `Table` object". With that signature someone
has to perform the lookup, and the only caller is a router — which would put a
rule and a refusal in the layer that is supposed to hold neither. A skeleton
binding to the old wording would produce exactly that router.

**The foreign-key posture of a rebuild** (plan 007). A batch recreate drops and
renames tables, so a Sync:

1. sets `PRAGMA foreign_keys = OFF` **outside** the transaction;
2. performs the rebuild inside one transaction;
3. runs `PRAGMA foreign_key_check` **before** committing and treats any returned
   row as a failure (`schema_apply_failed`);
4. restores `PRAGMA foreign_keys = ON` afterwards on **both** the success and the
   failure path.

Two reasons a reader will not infer. SQLite **silently ignores** a change to that
pragma inside a transaction, so the obvious ordering compiles and does nothing.
And the connection is **pooled**, so a Sync that left the pragma off would
disable foreign keys for every later request on that connection. This is the
**one code path that suspends** the per-connection `foreign_keys = ON` invariant
(Database access, above); an unrecorded suspension is the kind of thing a later
reader deletes.

**A rebuild that cannot complete completes not at all.** A failed cast, a
nullability tightening over existing NULLs, or a foreign-key violation rolls the
transaction back, leaves the table as it was, leaves no `_alembic_tmp_*` table
behind, and raises `schema_apply_failed` (US-018.AC-6, US-018.AC-7). What the
administrator sees and agrees to is `admin-surfaces.md`'s.

The flip condition is recorded in `overview.md`.

### The two transaction rules, and the asymmetry between them

**A memo write and its embedding write are one transaction**, and **a failed
embedding fails the whole transaction** for memo writes. That is the property the
`sqlite-vec` choice was made for: a service that commits the row and then embeds
in a follow-up transaction reintroduces exactly the drift the choice avoided, and
FEAT-005's check stays meaningful only while a memo with no vector is genuinely
an anomaly.

**Message and session writes do the opposite, deliberately.** US-112 is explicit:
with no embedding model configured, an edit to a settled entry **still saves**,
and the roleplayer is told search coverage is incomplete (UC-078's exception
flow). So:

| Write | Embedding unavailable (`no_embedding_model`) |
|---|---|
| memo create / body edit | **fails the transaction** — nothing is stored |
| message edit, settle, re-open (`session_vec`) | **succeeds, degraded** — the row is stored, the vector is left stale, the response says coverage is incomplete |

**This asymmetry is deliberate and is named here so nobody harmonises the two
later.** In short: a memo exists *in order to be retrieved*, so an unembedded one
is a note that silently does nothing; a settled entry is *the record of what
happened*, and an instance-level omission must not block a roleplayer's own
record-keeping. The full reasoning is in `search-and-retrieval.md`, which owns
the embedding lifecycle and carries the same table. The structural consequence
for this doc: **`no_embedding_model` has two callers** — one that lets it
propagate out of the transaction, one that catches it and reports degradation in
the write's own response.
