# Backend structure

**Realizes:** FEAT-001, FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-008,
FEAT-009, FEAT-010, FEAT-013, FEAT-018, FEAT-019, FEAT-020, UC-003, UC-012,
UC-013, UC-027, UC-035, UC-037, UC-050, UC-065, UC-066, UC-071, UC-078, UC-080,
UC-083, UC-084, UC-085, UC-086, US-132, US-134, US-135

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
    db/
      engine.py          # connection, PRAGMAs, sqlite-vec extension load
      schema.py          # the table-definition registry (data-model.md)
      drift.py           # PRAGMA introspection vs the registry (FEAT-005)
      sync.py            # the DDL executor: Alembic batch ops, admin-triggered
                         #   only — see "Schema evolution" below
    routers/
      health.py          # /api/health
      bootstrap.py       # FEAT-001
      auth.py            # FEAT-002, and /api/me
      admin_users.py     # FEAT-003
      admin_llm.py       # FEAT-004
      admin_db.py        # FEAT-005
      characters.py      # FEAT-006
      setups.py          # FEAT-007
      sessions.py        # FEAT-008, FEAT-013
      stream.py          # FEAT-009 + FEAT-010: the record, the zone, settle,
                         #   re-open, and the one SSE route
      memos.py           # FEAT-012
      search.py          # FEAT-017
      transfer.py        # FEAT-018
    services/
      bootstrap.py  auth.py  users.py
      llm_registry.py            # servers, models, enabled-model validation
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
        client.py                # one OpenAI-compatible client
        frames.py                # SSE frame emission
        tools.py                 # the three tool definitions + dispatch
      transfer.py                # export/import
    models/                      # pydantic request/response models
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
ROLE_LADDER: dict[Role, int] = {Role.roleplayer: 0, Role.admin: 1}

def require_role(min_role: Role) -> Callable[..., CurrentUser]: ...
```

A factory rather than one `require_admin` dependency because the check every
route wants to express is a **threshold** — "at least this rung" — so a new rung
is one ladder entry rather than a new dependency per role plus an audit of which
routes should have gained it.

`require_role(Role.admin)` sits on **every** route in `admin_users.py`,
`admin_llm.py` and `admin_db.py` — as a router-level dependency, not per handler,
so adding an admin route cannot forget it. The frontend's pre-mount gate
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
- Resolution happens **at call time**, not at registration and not at startup, so
  rotating a key is an environment change plus a restart — no database write, no
  re-registration.
- A missing environment variable is a **typed error** (`secret_ref_missing`), not
  a `None` that turns into an unauthenticated request against the provider.

Why this is right for RPHelper rather than merely inherited from BookWriter:
FEAT-018/UC-061 requires a whole-database export an administrator may move
between instances, and FEAT-019 makes that export deliberately opaque. A database
holding credentials would turn every export into a secret-bearing artifact and
every drift report into something needing redaction. With pointers, the export
moves configuration and the environment supplies credentials.

## The error model

**Realizes:** FEAT-004, FEAT-009, FEAT-010, FEAT-011, FEAT-013, UC-012, UC-032,
UC-037, UC-039

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

Wire shape for every non-2xx the SPA is expected to handle:

```json
{ "error": { "code": "model_not_enabled", "message": "...", "detail": { ... } } }
```

The named errors the design requires:

| `code` | Raised when | `detail` carries | Realizes |
|---|---|---|---|
| `model_not_enabled` | Use-time validation of a resolved model reference fails (R4) | the model reference, and **which level set it** — `character` or `session`, **never `user`**: there is no user-level model default (UC-050, R1's correction) | FEAT-004, UC-012 |
| `no_embedding_model` | An embedding is attempted with no designated embedding model, or the designation is gone (R4) | nothing user-scoped | FEAT-004, UC-013 |
| `secret_ref_missing` | `"$ENV_VAR"` names an absent variable | the variable name | FEAT-004 |
| `llm_unreachable` | Provider call fails or times out | provider-side message, no request body | FEAT-010, UC-032 |
| `tool_failed` | A tool invocation fails — **not surfaced as a stream error** (R9) | tool name | FEAT-014, FEAT-015, FEAT-016 |
| `translation_failed` | UC-039's exception flow; nothing is cached | the message id, as a string | FEAT-011 |
| `zone_empty` | Settle is attempted with nothing in the current zone (R11) | nothing | FEAT-010, UC-083 |
| `zone_not_empty` | Re-open is attempted while the session's current zone is not empty (R11, US-128) | nothing | FEAT-010, UC-037 |
| `nothing_to_reopen` | Re-open is attempted where the last settled row has no buried group — a pasted partner block (US-121) | nothing | FEAT-010, UC-037 |
| `message_not_editable` | An edit targets a **buried** row (US-116) | nothing | FEAT-010, UC-036 |
| `already_configured` | A bootstrap route is reached on a configured instance (UC-003) | nothing | FEAT-001 |
| `account_disabled` | Login by a disabled account (FEAT-002) | nothing | FEAT-002 |

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

The endpoint deliberately **touches the database** (a cheap `sqlite_master` read)
rather than returning a static `{"status":"ok"}`. A health check that cannot fail
tells an operator nothing, and FEAT-001's whole problem is an instance that is
running but not usable.

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
is already loaded.

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
| list available models | populates the models and embedding modals (UC-012, UC-013) | the model names the server offers |
| **test connection** | UC-011's own capability | a typed connection-test result |

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
or removes a registration. Its result is a **typed value**; the proposed value set
and its `_TBD:` are in `admin-surfaces.md`.

## Database access

One SQLite connection factory in `db/engine.py`, which on every connection:

- sets `PRAGMA foreign_keys = ON`,
- sets `PRAGMA journal_mode = WAL` — readers do not block the single writer,
  which matters because an SSE compose exchange holds a request open while other
  reads happen,
- loads the `sqlite-vec` extension, so `vec0` tables and the KNN operators are
  available on every connection rather than only where someone remembered.

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
   together or not at all".
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

Four facts, each stated because it is the one a reader would otherwise assume
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

**Where the executor lives: `db/sync.py`**, beside `db/schema.py` and
`db/drift.py`. It takes a drift-report row plus the registry's `Table` object
and emits the batch operations that close the gap; it holds no state of its own
and is called only from `routers/admin_db.py`'s Sync route. Diagnosis stays in
`db/drift.py` and remediation lives in `db/sync.py`, so the code path that only
reports cannot write.

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
