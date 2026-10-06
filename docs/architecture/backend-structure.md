# Backend structure

**Realizes:** FEAT-001, FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-006,
FEAT-007, FEAT-008, FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013, FEAT-014,
FEAT-015, FEAT-016, FEAT-017,
FEAT-018, FEAT-019, FEAT-020, UC-003, UC-006, UC-007, UC-008, UC-009, UC-010,
UC-011, UC-012, UC-013, UC-014, UC-015, UC-017, UC-018, UC-019, UC-020,
UC-023, UC-024, UC-025, UC-039, UC-042, UC-043, UC-044, UC-047, UC-048,
UC-049, UC-050, UC-065, UC-066, UC-067, UC-068, UC-071, UC-075, UC-076,
UC-077, UC-087, US-006.AC-3, US-018.AC-6, US-018.AC-7, US-107, US-112,
US-140, US-143

FastAPI application layout, the routers/services split, the id and JSON
boundaries, the roleplayer and admin route surfaces, configuration and secrets,
persistence access, and the error model that carries typed failures to the SPA.
Commands (`pytest`, `mypy app`, `ruff check .`) are in the root `CLAUDE.md`.

Two subjects were split out of this doc at the finalization of plans 008..032:
**`session-stream.md`** holds the stream routes, settle and re-open, the `(( ))`
seam, the compose route and its harness, the tool seam and the discussion read;
**`transfer.md`** holds the export/import contract and its route surfaces. Both
are cross-referenced below rather than restated.

## Layout

```
backend/
  .venv/
  app/
    main.py              # app factory, router registration, lifespan
    config.py            # pydantic-settings Settings + lru_cache accessor
    logging.py           # loguru sink configuration, the InterceptHandler, and
                         #   third-party logger suppression (_SILENCED_LOGGERS
                         #   beside _PROPAGATING_LOGGERS, plan 028);
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
      schema.py          # the table-definition registry + the four named
                         #   Core selectables over `messages` (data-model.md)
      search_tables.py   # the vec0 and FTS5 tables: ensure-on-write DDL and
                         #   the FTS triggers — OUTSIDE `metadata` (plan 024)
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
      characters.py      # FEAT-006 (plan 009)
      setups.py          # FEAT-007 (plan 010)
      sessions.py        # FEAT-008 (plan 011); owns the character-addressed
                         #   create-and-seed route (plan 018)
      stream.py          # FEAT-009 + FEAT-010: the record, the zone, settle,
                         #   re-open, the one SSE route, the discussion read,
                         #   and the chat-client / tool-registry dependencies
                         #   (session-stream.md)
      configuration.py   # FEAT-013 (plan 017) — seven routes incl. /api/models
                         #   and /api/me/settings
      translation.py     # FEAT-011 (plan 023) — the one translate route
      memos.py           # FEAT-012 (plans 015, 016)
      search.py          # FEAT-017 (plan 029) — the one my-search route
      transfer.py        # FEAT-018 — export (plan 030) and import (plan 031);
                         #   contract in transfer.md
    services/
      health.py                  # /api/health's probe SQL — NOT a domain service; see
                                 #   "Routers versus services" (decided in plan 001)
      bootstrap.py  auth.py  users.py
      passwords.py               # the password-hashing seam: hash + verify (plan 003)
      llm_registry.py            # servers, models, the probe primitive, designation,
                                 #   the enabled set and first-enabled order, and
                                 #   BOTH use-time validators (plan 006). The
                                 #   embedding validator has callers since plan 024;
                                 #   the chat validator since plan 017/021
      configuration.py           # FEAT-013 (plan 017): R1's two chains, the
                                 #   configuration reads/writes, resolve_model_for_use
      memo_chain.py              # R2 — resolve_chain + memo_reach (plan 015), and
                                 #   the public chain CLAUSE BUILDER beside them
                                 #   (plan 026): the single home of the chain
                                 #   predicate (domain-rules.md R2)
      characters.py  setups.py
      sessions.py                # incl. start-a-session-by-writing (UC-080):
                                 #   create + capture the model + seed the zone in
                                 #   ONE transaction (session-stream.md)
      messages.py                # append to the zone, append an assistant row
                                 #   (append_assistant_message), edit text, file a
                                 #   partner block, read a settled entry's buried
                                 #   group (list_discussion), derive the tool view
      settle.py                  # settle + re-open — the ONLY writers of the burial
                                 #   and settle columns
      parens.py                  # the (( )) parser: classify + strip. Pure, no I/O
      memos.py                   # FEAT-012 (plan 015) + the reorder (plan 016)
      context.py                 # context assembly (plan 020): the system-prompt
                                 #   renderer, the message mapper and
                                 #   assemble_context. NO router; its only caller
                                 #   is compose.py (llm-and-streaming.md)
      compose.py                 # the compose source (compose_stream) and the
                                 #   handler-side begin_compose (plan 021)
      translation.py             # FEAT-011 (plan 023)
      embedding.py               # the embed call + vector upsert/delete (plan 024)
      session_index.py           # session_vec composition + the fan-out (plan 024)
      tools/                     # the tool seam (plan 021 — session-stream.md)
        definitions.py           # the three tool declarations
        seam.py                  # ToolScope, ToolOutcome, the Tool protocol, the
                                 #   registry, offered_tools, dispatch
        memo_search.py           # the memo_search Tool adapter + its formatter
                                 #   (plan 026)
        session_search.py        # the session_search adapter + formatter (plan 027)
        web_search.py            # the web_search adapter, its formatter, and the
                                 #   factory that decides "configured" (plan 028)
      web_search/                # the web-search provider seam (plan 028)
        provider.py              # the web-result value + the provider protocol
        google.py                # the Google Custom Search provider
      search/                    # the hybrid search port (plan 025) and its callers
        ports.py                 # the contract: SearchScope variants, SearchHit,
                                 #   and the pure helpers (search-and-retrieval.md)
        candidates.py            # the filters-first candidate selects
        lexical.py               # the FTS5 arm
        vector.py                # the vec0 arm (embeds the query)
        hybrid.py                # `search` — the arms plus RRF
        memo_search.py           # the result-count constant, the memo extra
                                 #   predicate and the sync search_memos (plan 026)
        session_search.py        # the cap and excerpt-length constants, the session
                                 #   predicate factory, the sync search_sessions, and
                                 #   the sync owner-scoped excerpt read (plan 027)
        my_search.py             # the two LIKE corpora, hydration, run_my_search
                                 #   (plan 029)
      llm/
        client.py                # one OpenAI-compatible client, httpx.AsyncClient;
                                 #   chat_stream, embed, the delta values, and the
                                 #   probe-outcome value set (plans 006, 021, 024)
        chat.py                  # ChatMessage (four roles), ToolCall,
                                 #   to_wire_message, the <think> literals and
                                 #   strip_think (plans 020, 021). Deliberately
                                 #   NEUTRAL: the chat-message value type and the
                                 #   role literal live here, not in context.py,
                                 #   so client.py imports them without importing
                                 #   the assembler (020 D9)
        frames.py                # SSE frame types + encoder, the streaming harness
                                 #   (frame_stream, sse_response) and
                                 #   own_connection_persister (plans 019, 021)
      transfer.py                # export only — read-only by design (plan 030)
      transfer_import.py         # validation, deserialization, the remap engine,
                                 #   the three roleplayer imports, the database
                                 #   replace (plan 031 — transfer.md)
    models/                      # pydantic request/response models; ids.py holds
                                 #   the id aliases, secret_ref.py the "$"-pointer
                                 #   field type (plan 006); memos.py,
                                 #   configuration.py, translation.py, transfer.py,
                                 #   search.py (my-search's response models, 029)
  tests/
```

`routers/entries.py` and `routers/discussions.py` are **gone**, with the
`discussions` table (`data-model.md`); `services/entries.py` and
`services/discussion.py` go with them. `services/llm/stream.py` is renamed
`frames.py` so that `routers/stream.py` is the only `stream` module in the
backend — two modules with one name across two packages is an import ambiguity
nobody needs.

Two placements are worth stating because the obvious alternative was taken and
rejected. **The streaming harness lives in `services/llm/frames.py`, beside the
frame types, rather than in a module of its own** (019 D1): its whole job is to
drive a stream of frame values and the two belong together. And **the tool seam
is the package `services/tools/`, not the single `services/llm/tools.py` this
doc first sketched** (021 D6): the declarations, the protocol and the registry
are three separable things, and the declarations in particular must be editable
without touching an implementation.

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

### The two named exceptions to "routes return and take pydantic models"

Both belong to FEAT-018 and both are named so nobody "fixes" them into a model
that cannot exist (`transfer.md` has the full contract):

- **The export routes return a raw `Response`** (plan 030), because the envelope
  is column-agnostic: its payload keys are whatever `metadata` currently
  declares, and no static model can describe that. The id boundary still holds,
  because `services/transfer.py`'s serializer stringifies every id **before the
  router sees the body** — which is also why the serializer carries its own
  id-column predicate (primary key, or a foreign key, or a name matching `id` /
  `*_id`) rather than relying on `models/`.
- **The import routes take a raw JSON object body** (plan 031), for the same
  reason read backwards. The service's deserializer parses the ids inside it and
  accepts **decimal strings only**; the responses are ordinary pydantic models
  using `SnowflakeOut`.

Plan 030 recorded a flip condition — "if a second raw-dict route appears, extract
the serializer into `models/` as the shared mechanism" — and plan 031
**discharged it**: the deserializer reuses 030's id-column predicate, so the
shared mechanism turned out to be the predicate, not a module move. No third raw
route exists, and a third would be the point to revisit this.

### Request validation that is not a domain error

Set by plan 009 as the precedent every later roleplayer form follows (009 D8):

- **A blank or whitespace-only required text field is stripped and refused by
  pydantic — FastAPI's own 422, with no domain error code.** `characters.name`
  was the first; `messages.text`, a memo `body` and `opening_message` all follow
  it. A domain code would be a second vocabulary for something the framework
  already answers precisely.
- **Unknown body keys are ignored**, not refused. A client sending a field the
  server has not grown yet is a version skew, not an error.
- **A query parameter is a plain typed parameter with a default, placed last, and
  carries no `Query(...)` wrapper.** `include_archived` on `GET /api/characters`
  was the first query parameter in any router (before it every admin router
  asserted there was none), and its position is forced: the only defaulted
  parameter must come after the `Annotated[..., Depends(...)]` ones. Recorded so
  the next router does not re-derive it.

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

### Two service-module idioms, copied deliberately rather than shared

Named here because the duplication **is** the convention today and a reader will
otherwise read it as an accident, or "fix" it into a shared module that every
service then imports — which is the hub this layer exists to avoid:

- **`_now_text()`** — the one-instant-per-operation timestamp helper, in the
  fixed-width form `data-model.md` requires. Each service carries its own private
  copy.
- **`_reading`** — the read-rollback context manager, which ends an autobegun
  read's implicit transaction so a later `begin()` on the same connection does
  not raise ("Transactional DDL", below, has the mechanism). First in
  `llm_registry.py`, then `characters.py`.

Each new service copies both rather than importing them, so that a service module
remains a leaf that imports no sibling. If that ever stops being worth it, the
destination is a top-level leaf beside `ids.py` — not another service.

### A service verifies its own parent, in its own transaction

Set by plan 010 (D6) and held by plans 011, 012, 015 and 018: **a service
verifies a parent — and a chosen child of that parent — with its own
owner-scoped `select` inside its own transaction, and never calls another
service's operation to do it.** `services/setups.py` checks the character,
`services/sessions.py` checks the character and the setup, `services/memos.py`
checks the target level.

The reason is transaction ownership, not tidiness. A service owns its
`with conn.begin():` block; calling a sibling's *operation* would either nest a
`begin()` or split one decision across two transactions, and both break the
"these writes commit together or not at all" claims the Core decision was taken
for. `services/messages.py` and `services/settle.py` are the sharpest case — two
services over **one table** that never import each other, each with its own
owner-scoped session check and its own `last_used_at` bump (012 D11).

**The naming rule that goes with it:** RP-session vocabulary never collides with
`services/auth.py`'s login-session vocabulary (`RpSession`, `start_session`, …).
`data-model.md` keeps the tables apart (`sessions` versus `auth_sessions`) for
the same reason; the collision risk is permanent, and the next contributor will
meet both modules.

### The one narrow service-to-service import exception, named as a pattern

Stated as a **pattern** rather than a list of cases, because the list grows with
almost every feature and a reader meeting the next instance should recognise it
from the rule rather than from the table:

> A service may import another service's **transaction-neutral** parts — a value
> type, a row mapper, a read that opens no transaction of its own, or an insert
> helper that checks nothing and bumps nothing. It may never import an
> *operation*, because an operation owns a transaction.

The rule protects transaction ownership, and nothing in that list touches it.
The instances, so each is visibly deliberate rather than a leak:

| Importer | Imports | Plan |
|---|---|---|
| `memo_chain.py` | `memos.py`'s `Memo` value type and its row mapper only | 015 D11 |
| `configuration.py`, `sessions.py` | `llm_registry.py`'s transaction-neutral reads, `ModelRefLevel`, `EnabledChatModel`, `UNSET` | 017 D12 |
| `sessions.py` | `messages.py`'s zone-insert helper and message value type — the same helper `append_message` uses, so the zone insert exists once | 018 D3 |
| `context.py` | read operations from `sessions`, `characters`, `configuration`, `memo_chain` and `messages` | 020 D9 |
| `compose.py` | `configuration`, `context.py` (the assembler), `messages`, `llm_registry`, `tools`, `llm.*` | 021 D15 |
| `tools/seam.py` | `sessions`, `messages`, `configuration` types | 021 D15 |
| `translation.py` | `configuration`, `llm_registry`, `llm.chat`, `llm.client` | 023 |
| `memos`, `settle`, `messages`, `characters`, `setups` | `embedding.py` / `session_index.py` | 024 D9 |
| `search/vector.py` | `embedding.py` — the vector arm embeds the query | 025 |
| `search/memo_search.py` | `memo_chain.py`'s chain clause builder, and the port | 026 D2 |
| `tools/memo_search.py` | `search/memo_search.py` | 026 D3 |
| `tools/seam.py` | `tools/memo_search.py`, `tools/session_search.py` — for registration | 026, 027 |
| `search/session_search.py` | the port, and `settled_entries` from `db/schema.py` | 027 D6 |
| `tools/session_search.py` | `search/session_search.py` | 027 D6 |

**None of the search or tool importers opens a transaction of its own**, which is
why each is inside the pattern rather than an exception to it: the port and the
tools take a connection and run reads on it, and the seam owns the short-lived
connection they run on (`session-stream.md`).

**`services/context.py` is the widest of these rows and is inside the pattern for
the same reason** (020 D9). It imports **read operations** from five services,
which reads like the thing the rule forbids — and the rule's reason is what
settles it: the no-import rule protects **transaction ownership**, and
`context.py` **opens no transaction of its own and calls only reads that leave
none open**. So there is no transaction for a caller to nest into or split across,
and nothing the rule is protecting is at risk. It is a **read composition**,
exactly like `compose.py` — which is also its only caller. Spelled out because the
table above otherwise claims to list every instance of the pattern while showing
one that looks like a breach of it.

**One of these imports goes the other way at runtime and is deliberately
type-checking-only** (026 D3, 027 D6). The two tool adapters import the seam's
types **under `TYPE_CHECKING`** rather than at runtime, because `tools/seam.py`
imports the adapters in order to **register** them — a runtime import back would
be a cycle. Named so it is not "tidied" into an ordinary import: the cycle is
real, and the registry's direction (seam knows its tools, tools do not know the
registry) is the direction that keeps the registry the single place a tool becomes
available.

**`app/errors.py` is the framework-coupled leaf every service may import**, and
that is the one deliberate hole in "a service never imports `fastapi`".
`errors.py` imports `fastapi` at module level, so importing any service that
raises a typed error puts `fastapi` in `sys.modules`. The consequence is a
testing rule, not a design change: **framework-freedom here is a source-level
property — a "no web framework in `services/`" check must read the module's own
imports and never `sys.modules`** (observed in plan 027, true of plan 026's
`memo_search.py` since it shipped).

**No service module touches a third-party logger.** `app/logging.py` owns
third-party logger suppression — the constant `_SILENCED_LOGGERS` beside
`_PROPAGATING_LOGGERS` — and it is the only place either list may grow
(plan 028). The reason is the stdlib bridge: `configure_logging` routes every
stdlib record into loguru, so a library that logs a request URL logs it into both
sinks. Plan 028 was the first feature to put message text in a query string and
found `httpx`'s own request record carrying it at `DEBUG`. A service that
silenced its own dependency's logger would make the redaction surface depend on
import order (`deployment.md`'s redaction rule).

### Every route is classified, at build time

**A new API route must be added to the privacy guard's classification table —
`public` / `self` / `registry` / `owner` / `admin` — or the build fails**
(plan 032, `backend/tests/test_privacy_audit_routes.py`). This is a build-time
contract, not a review convention: an unclassified route is a failing test, and
the route enumeration it checks against lives in
`docs/plans/032.privacy-isolation-audit/context.md`.

It exists because R5 is a *query-level* property and therefore invisible to any
single reviewer's reading. The companion rule the guard also pins is **refusal
identity: a foreign id produces a response identical to an unknown id** — same
code, same status, same body. Every `*_not_found` code in the error model below
depends on that, and it is the property that keeps a guessable snowflake
(`data-model.md`) from leaking existence.

### The two service reads that take no `user_id`

`require_user` yields the `user_id` that every service call is scoped by, and a
service touching user-owned data takes it as a **required positional argument**.
**`export_database` and `import_database` are the only exceptions** — the
read-side and write-side twins of one deliberate hole (plans 030, 031). They are
reachable only from an admin route, and they stay R5-compatible through
**opacity** rather than scoping: no viewer, no preview, no search, no diff, no
count. `import_database`'s single-admin guard lives in the service, not the
router. Recorded here so a reviewer auditing "every read takes `user_id`" finds
the exception stated rather than discovering it; `transfer.md` has the reasoning.

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
  **Since plan 024 it also holds `get_llm_client_factory`**, which
  `routers/admin_llm.py` re-imports rather than declaring its own: a second
  declaration would be a second override point, and a test overriding one would
  silently miss the other. Every route that embeds depends on it plus
  `get_settings`; the services underneath take the factory and the timeout as
  **keyword-only parameters with defaults**, so they stay callable with no
  FastAPI in sight.

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
scope becomes a type error rather than a privacy incident. The two named
exceptions are above.

**`routers/characters.py` was `require_user`'s first router-level consumer**
(plan 009) — before it the dependency existed with no caller, exactly as
`require_role` did before plan 005 — and every roleplayer router since attaches
it the same way, at router level rather than per handler, so adding a route
cannot forget it. One consequence is worth stating because it reads as a gap:
**an administrator owns characters, setups, sessions and memos like any other
account**, scoped by their own `user_id`. The ladder grants nothing here. An
admin calling a user-content route is an **ordinary owner and never a
super-reader** (asserted by plan 032's audit; previously implicit).

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

**`/api/admin/database` — `routers/admin_db.py` (plan 007), plus the two
transfer routes (plans 030, 031).** Five routes:

| Route | Answers |
|---|---|
| `GET /api/admin/database/tables` | **200**, the whole drift report |
| `POST /api/admin/database/tables/{table_name}/create` | **200**, the per-table report **re-derived after the apply** |
| `POST /api/admin/database/tables/{table_name}/sync` | the same |
| `GET /api/admin/database/export` | **200**, the whole-database export as a JSON file attachment (plan 030, `transfer.md`) |
| `POST /api/admin/database/import` | **204**, and the session cookie cleared (plan 031, `transfer.md`) |

The first three take no body and no query parameter. The import is **the first
admin-database route that takes a body**, and it is a raw JSON object rather
than a pydantic model — one of the two named exceptions above. Neither transfer
route needs a per-handler guard: `require_role(Role.admin)` is on the router.

- **Each apply answers with the re-derived row**, giving US-018.AC-2 a
  server-side witness beside the page's re-load.
- **`{table_name}` is validated by lookup in the registry inside `db/sync.py`,
  never in the router**, and the raw string is never interpolated into SQL — only
  the registry's own `Table` object reaches the DDL. That is what makes a non-id
  path parameter safe here, and it is the one thing a later contributor could
  undo by "simplifying" the lookup into the handler.
- **Two routes rather than one `apply`**, because the UI offers them under
  different conditions and only one of the two can lose data.
- **The one admin route family not keyed on a snowflake** — its drift wire
  carries no id at all, so the JSON id boundary has no call site on the three
  drift routes.

#### The roleplayer route surfaces

**Realizes:** FEAT-006, FEAT-007, FEAT-008, FEAT-011, FEAT-012, FEAT-013,
FEAT-017, UC-017, UC-018, UC-019, UC-020, UC-023, UC-024, UC-025, UC-039,
UC-042, UC-043, UC-044, UC-047, UC-048, UC-049, UC-058, UC-059, UC-060, UC-067,
UC-068, UC-075, UC-076, UC-077

Every router below carries **router-level `require_user`** and groups **by
feature, not by path prefix** — which is why `routers/memos.py` owns a route
whose path starts `/api/sessions/`, and `routers/sessions.py` owns one whose
path starts `/api/characters/`. Three shapes repeat across all of them and are
stated once: **lists are wrapped** (`{ characters: [...] }`, `{ setups: [...] }`,
`{ sessions: [...] }`, `{ memos: [...] }`) so a list response can grow a sibling
key without becoming a breaking change; **no entity has a `DELETE`** except a
memo, so an attempted delete is FastAPI's own 405; and **archive and restore are
named action routes**, never a `PATCH` of a status field, so that each hangs off
its own rule.

**`/api/characters` — `routers/characters.py` (plan 009).** The first
roleplayer-owned family, and the shape plans 010 and 011 copied.

| Route | Notes |
|---|---|
| `GET /api/characters` | takes `include_archived`; order `created_at DESC, id DESC` |
| `POST /api/characters` | **201** |
| `GET` / `PATCH /api/characters/{character_id}` | `PATCH` treats a null key as absent, and an empty `PATCH` is a no-op |
| `POST /api/characters/{character_id}/archive` · `/restore` | idempotent (R6) |
| `GET` / `PATCH /api/characters/{character_id}/configuration` | plan 017; `model: null` clears |
| `GET /api/characters/{character_id}/export` | plan 030, `transfer.md` |
| `POST /api/characters/{character_id}/import` | plan 031, `transfer.md` |
| `POST /api/characters/{character_id}/sessions` | owned by `routers/sessions.py` — `session-stream.md` |

**An administrator owns characters like any other account**, scoped by their own
id (009 D6). The role ladder governs the admin routers; it grants nothing on a
roleplayer route, and an admin calling one is an ordinary owner.

**`/api/characters/{id}/setups` and `/api/setups/{id}` —
`routers/setups.py` (plan 010).** `GET` / `POST` on the nested collection (with
`include_archived`), `GET` / `PATCH` on the flat single resource, plus
`…/archive` and `…/restore`. **Nested collection, flat single resource** is the
deliberate shape: a setup is always created *under* a character, and a setup's
`character_id` is **fixed for its life** — no route moves one between characters
— so addressing an existing setup through its parent would be a second way to
say something immutable. A missing or foreign parent answers
`character_not_found`; `character_id` is not patchable; listing and creating
under an **archived** character are allowed (R6 does not cascade).

**`/api/sessions` — `routers/sessions.py` (plan 011).**
`GET /api/sessions`, `GET` / `POST /api/characters/{character_id}/sessions`,
`GET /api/sessions/{session_id}`, `…/archive`, `…/restore`,
`GET /api/sessions/{session_id}/export`. **No `PATCH` and no `DELETE`**:
configuration is written through `…/configuration`, not through the session
resource, so there is deliberately no general session patch (017 D9). Lists order
`last_used_at DESC, id DESC`, and every session carries `setup_name` — the
referenced setup's **current** name by an owner-scoped LEFT JOIN, shown even when
the setup is archived, so a rename relabels every session with no fan-out write
(011 D10).

**`/api/memos` — `routers/memos.py` (plans 015, 016).**

| Route | Notes |
|---|---|
| `GET /api/memos?scope&scope_id` | one level |
| `POST /api/memos` | **201**; flags on the body are ignored — a memo is created enabled and not forced (R3, US-053) |
| `PATCH /api/memos/{memo_id}` | any subset of `body`, `is_enabled`, `is_forced`; a `null` key is "not supplied" |
| `DELETE /api/memos/{memo_id}` | **204** — the only delete path in the product (R6's contrast) |
| `PUT /api/memos/order` | body `{ scope, scope_id?, memo_ids: [string] }`; **200** `{ memos: [...] }` in the given order with `sort_key` 0..n-1 |
| `GET /api/sessions/{session_id}/memo-chain` | three or four levels in fixed order (R2) |

The nine-key `Memo` carries `scope_id` null for the user level and **never
`user_id`**. **One reorder request is one level**, which is what makes a
cross-level move inexpressible rather than merely refused (`US-103.AC-2`) — the
body names a scope, so there is no second level for a note to land in. It is
declared **before** the `{memo_id}` handlers so `order` is not read as an id.

**`/api/me/settings`, `/api/models` and the configuration routes —
`routers/configuration.py` (plan 017).** Seven routes. `GET /api/me` is
**unchanged** and still returns identity alone; user settings are their own pair
at `GET` / `PATCH /api/me/settings` (017 D14), because identity is read on every
mount and settings are not.

**`POST /api/messages/{message_id}/translation` — `routers/translation.py`
(plan 023).** An `async def` handler with its own overridable chat-client factory
dependency, **no request body** — the target language is resolved server-side
from the session's chain — and a 200 `{ message_id, target_language, text,
cached }`.

**`GET /api/search` — `routers/search.py` (plan 029).** One route, my-search's
(FEAT-017, UC-058..UC-060):

| | |
|---|---|
| Request | `GET /api/search?q=<text>` — a **sync `def`** handler behind router-level `require_user`, taking the shared client factory and the configured timeout |
| 200 | `{ characters, setups, sessions, entries, memos }` — five lists, **ids as strings** (the JSON id boundary) |
| Blank `q` | **five empty lists, and no embedding call at all** |
| Errors | **401**; **409** `no_embedding_model`; **502** `llm_unreachable` and `secret_ref_missing` |

Three things in that table are decisions rather than mechanics:

- **A blank `q` performs no provider call.** It is not "a search for nothing"
  answered from an index; the handler returns the empty shape before any arm
  opens the model. A page that mounts with an empty box would otherwise embed the
  empty string and bill for it (`frontend-structure.md` keeps the matching
  client-side rule, so neither side relies on the other).
- **The error set is the port's, propagated** — my-search adds no code of its own.
  It **fails whole** rather than returning the groups it could answer
  (`search-and-retrieval.md` has the reasoning), which is why a 409 or a 502 here
  means *no* results rather than *fewer*.
- **It is a sync `def`**, like every other roleplayer route, which is what lets
  the port's `asyncio.run` embed bridge work underneath it (the first-async-code
  rule below: these routes must stay sync).

**Router registration order is positional, and it is recorded** (plan 029): the
search router is included **after** the routers that preceded it at build time,
and `main.py`'s docstrings name it. There is no prefix collision to manage —
`/api/search` is its own segment — so the order carries no behaviour; it is
recorded only so that a reader comparing `main.py` to this layout finds the list
in the order they expect.

**Export and import** are `routers/transfer.py`'s; the routes and their contract
are in `transfer.md`.

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

## The session stream — moved to its own doc

**The stream routes, settle and re-open, the `(( ))` seam, the compose route and
its streaming harness, the tool seam and the buried-discussion read now live in
`session-stream.md`.** They were split out at the finalization of plans 008..032,
because this doc had come to carry two subjects: the FastAPI application's shape
and the session stream's behaviour.

What stays here is the application shape those routes sit in — the layout, the
routers/services split and its named exceptions, the JSON id boundary, the error
model and the per-code status record for every code the stream raises
(`zone_empty`, `zone_not_empty`, `nothing_to_reopen`, `message_not_editable`,
`message_not_found`, `tool_failed`, `no_model_enabled`, `model_not_chosen`), and
the transaction rules the degraded embedding path depends on.

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

    # web search (plan 028) — NOTE the aliases carry NO RPHELPER_ prefix,
    #   deliberately; see the named exception below
    search_cse_key: SecretStr | None = Field(default=None, validation_alias="SEARCH_CSE_KEY")
    search_cse_id:  str | None       = Field(default=None, validation_alias="SEARCH_CSE_ID")
    # ... one field per setting, each with an explicit alias

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

### The two web-search fields — a named exception to the `RPHELPER_` prefix

**`SEARCH_CSE_KEY` and `SEARCH_CSE_ID` are the only two settings whose aliases do
not start with `RPHELPER_`, and the exception is deliberate and user-confirmed**
(028 D2, U2). They are **the user's existing environment variable names**, already
set on the machines this project runs on, and renaming them would mean editing
every environment that works today.

**The explicit-alias rule itself still holds** — each field names its variable, so
the environment contract stays greppable and a field rename cannot silently rename
an operator-facing variable. **Only the prefix differs.**

**Written down because the "fix" is silent.** Changing these to
`RPHELPER_SEARCH_CSE_KEY` / `RPHELPER_SEARCH_CSE_ID` breaks nothing loudly: the
fields are optional, so the application starts, and the only symptom is that
`web_search` stops being offered — on every instance that was working. There is no
error to search for.

Two further properties:

- **The key is a secret-string type and is masked in `repr`**, so a settings dump
  or an exception that renders the model cannot print it (`deployment.md`'s
  redaction rule forbids API keys in logs; this is the mechanism that makes it
  hard to do by accident).
- **`routers/stream.py`'s registry dependency is the only reader of either
  field** (028 D3). The registry builder in `tools/seam.py` and the adapter's
  factory take **plain strings**, so no service module reads `Settings` — which is
  the convention this doc states for every service, held here rather than quietly
  excepted for a credential.

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

### The web-search credential deliberately is NOT a pointer

**`SEARCH_CSE_KEY` is a secret, and it does not use this pattern** (028 D2). It
is a plain `Settings` field read straight from the environment.

That is consistent rather than inconsistent, once the reason for pointers is read
precisely: **pointers exist because the rows that would otherwise hold the secret
are exported.** `llm_servers` travels in a whole-database export, so its
credential must not be a value. **A `Settings` field is never stored and never
exported** — it has no row, no drift report entry and no place in an envelope —
so there is nothing for a pointer to protect it from. Adding one would mean a
pointer resolving an environment variable from a value that itself came from the
environment.

**Rotation is identical either way**: an environment change plus a restart. No
database write, no re-registration. So the two mechanisms differ in storage and
agree in operation, which is why the difference is recorded here rather than
treated as a gap to close in one direction or the other.

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
| `model_not_enabled` | Use-time validation of a resolved model reference fails (R4), **and** set-time validation of a character- or session-level model override (plan 017) | the model reference — **the server id as a decimal string and the model name** — and **which level set it**, constrained to `character` or `session`, **never `user`**: there is no user-level model default (UC-050, R1's correction) | FEAT-004, FEAT-013, UC-012, UC-077 |
| `no_model_enabled` | Use time: **no model is enabled on the instance at all** | nothing | FEAT-013, US-107 |
| `model_not_chosen` | Use time: the session holds **no captured model** (both columns NULL) | nothing | FEAT-013, UC-077, US-144 |
| `no_embedding_model` | An embedding is attempted with no designated embedding model, or the designation is gone, or the designated model is not also enabled (R4); **since plan 024 also when the live `vec0` table's declared dimension does not match the designation's** | nothing user-scoped — and, for the dimension case, `{"reason": "dimension_mismatch"}`, which is instance-level rather than user-scoped | FEAT-004, UC-013 |
| `secret_ref_missing` | `"$ENV_VAR"` names an absent variable | the variable name | FEAT-004 |
| `username_taken` | An account is created with a username that already exists | nothing | FEAT-003, UC-006 |
| `user_not_found` | An admin route addresses an account id that does not exist | nothing | FEAT-003, UC-007, UC-008, UC-009, UC-087 |
| `self_role_change_refused` | A role change whose target is the acting administrator | nothing | FEAT-003, UC-087, US-140.AC-2 |
| `llm_server_not_found` | An admin LLM route addresses a server id that does not exist | nothing | FEAT-004, UC-010..UC-013 |
| `unknown_table` | A drift-page apply route names a table the registry does not declare | the table name | FEAT-005, UC-015 |
| `schema_apply_failed` | A `Create` or a `Sync` could not be applied — a driver error, a failed cast, or a `PRAGMA foreign_key_check` violation | the table name and the operation (`create` \| `sync`); **never the driver's message** (below) | FEAT-005, UC-015, US-018.AC-6, US-018.AC-7 |
| `llm_unreachable` | Provider call fails or times out | provider-side message, no request body | FEAT-010, UC-032 |
| `tool_failed` | A tool invocation fails — the tool is not offered, the name is unknown, the arguments are not an object, or `run` raises. **Since plan 028 the web-search provider and its adapter raise it directly too**, for every provider failure. **Not surfaced as a stream error** (R9): it becomes a `tool_fail` frame and the loop continues | the tool name — for web search exactly `{"tool": "web_search"}`, and **never chained to the transport exception** (below) | FEAT-014, FEAT-015, FEAT-016, UC-051, UC-053 |
| `translation_failed` | UC-039's exception flow; nothing is cached | the message id, as a string | FEAT-011 |
| `zone_empty` | Settle is attempted with nothing in the current zone — **or with a zone holding only `role='tool'` rows** (R11); also the textless retry compose when no non-tool zone row exists | nothing | FEAT-010, UC-083 |
| `zone_not_empty` | Re-open is attempted while the session's current zone is not empty (R11, US-128) | nothing | FEAT-010, UC-037 |
| `nothing_to_reopen` | Re-open finds **no settled row at all**, or a last settled row with **no buried group** — a pasted partner block, a lone directly-settled turn, or a lone decision (R11) | nothing | FEAT-010, UC-037 |
| `message_not_editable` | An edit targets a **buried** row (US-116) **or a `role='tool'` row** (`US-115.AC-1`'s `Constraint:`). Those are the only two meanings | nothing | FEAT-010, UC-036 |
| `message_not_found` | A message route addresses an id that does not exist or belongs to another user; also the discussion read on a zone row, a buried row or a non-settled id | nothing | FEAT-009, FEAT-010, UC-036, UC-078, UC-083 |
| `character_not_found` | A character route (or a child route's parent check) addresses an id that does not exist **or belongs to another user** | nothing | FEAT-006, UC-018, UC-067 |
| `setup_not_found` | As above, for a setup | nothing | FEAT-007, UC-020, UC-068 |
| `setup_archived` | A session start names the caller's **archived** setup (R6 does not cascade, but a new session may not adopt one) | nothing | FEAT-007, UC-021 |
| `session_not_found` | As above, for a session | nothing | FEAT-008, UC-024, UC-025 |
| `memo_not_found` | A memo `PATCH` or `DELETE` addresses an id that does not exist **or belongs to another user** | nothing | FEAT-012, UC-044 |
| `memo_order_mismatch` | A reorder's `memo_ids` is not **exactly** the caller's notes at that level — missing, extra, foreign, nobody's, or duplicated: the client's view is stale | nothing — **it never lists the mismatched ids** (R5) | FEAT-012, UC-076 |
| `export_invalid` | An import body is malformed or incompatible | exactly `{"reason": …}`, one of `not_an_export`, `unsupported_version`, `schema_mismatch`, `wrong_granularity`, `malformed_payload`; **never a table name, a column name or row content** (R5), and never the driver's message | FEAT-018, UC-061..UC-064 |
| `database_not_empty` | A whole-database import reaches an instance holding content (`US-077.AC-3`) | nothing | FEAT-018, UC-061 |
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
`current_zone` selectable. Same product guarantee, different predicate, so the same
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
- **A `tool_failed` raised for web search is never chained to the transport
  exception** that caused it (plan 028, D5), and carries **no query, no key, no
  URL and no response body**. The chaining is the point: a chained cause puts the
  request URL into any traceback that is ever formatted, and for this one tool the
  URL contains the query — which is message-derived text (`deployment.md`'s
  redaction rule names web-search queries explicitly). So the raise is
  deliberately lossy, and the loss is the feature.

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
| `character_not_found` | **404** | the path's id addresses no row **for this caller**; another user's row answers identically to a nonexistent one, so existence never leaks (R5, refusal identity) | plan 009 |
| `setup_not_found` | **404** | as `character_not_found`, indistinguishable for "nobody's" and "another user's" | plan 010 |
| `session_not_found` | **404** | the same | plan 011 |
| `setup_archived` | **409** | well formed, the caller owns the setup, and the setup's state conflicts with the operation — the shape of `username_taken`. **Not 404:** the setup exists for the caller, and saying otherwise would make "restore it and try again" undiagnosable. **Not 422:** no field is malformed | plan 011 |
| `zone_empty` | **409** | well formed, the caller owns the session, the **stream's state** conflicts. Not 404 (the target exists), not 422 (nothing malformed) | plan 012 |
| `zone_not_empty` | **409** | as `zone_empty` | plan 012 |
| `nothing_to_reopen` | **409** | as `zone_empty` | plan 012 |
| `message_not_editable` | **409** | as `zone_empty` | plan 012 |
| `message_not_found` | **404** | the sibling of `session_not_found`: the path's id addresses no row of the caller's | plan 012 |
| `memo_not_found` | **404** | the same sibling | plan 015 |
| `memo_order_mismatch` | **409** | well formed and owned; the submitted order conflicts with the level's actual membership | plan 016 |
| `no_model_enabled` | **409** | as `model_not_enabled`: a well-formed request against conflicting **registry** state | plan 017 |
| `model_not_chosen` | **409** | as above, against conflicting **session** state | plan 017 |
| `tool_failed` | **502** | a dependency's failure, like `llm_unreachable`. **Never an HTTP response as built** — it is the `tool_fail` frame's code — but the status is recorded where the code is born, so the first route that does raise it answers consistently | plan 021 |
| `translation_failed` | **502** | a dependency's failure, like `llm_unreachable` | plan 023 |
| `export_invalid` | **400** | the body is malformed or incompatible. The codebase's **first typed 400**: everything else malformed is FastAPI's own 422, but the SPA must tell "not an export" from "too old" without parsing prose, and a 422's shape is the framework's, not this error model's | plan 031 |
| `database_not_empty` | **409** | a well-formed request that conflicts with instance state — the same shape as `already_configured` | plan 031 |

**The five stream codes each carry a fixed default `message`**, following
`already_configured`'s pattern (012 D13), so that a code raised with no arguments
still renders a non-empty `message` on the wire. Whether a later code adopts the
pattern stays a per-code decision by the feature that introduces it.

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

**It is unchanged by FEAT-013, deliberately.** The user's two language settings
live at their own `GET` / `PATCH /api/me/settings` pair (017 D14) rather than on
this route, because identity is read on every mount of two entries and the
settings are read on one screen; widening this payload would make every mount pay
for a screen most of them never show. The settings write stamps `users.updated_at`
in the fixed-width timestamp form (`data-model.md`).

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

**The second async consumer goes the other way** (plan 024). The embedding
writes are **sync services that call `LlmClient.embed` through
`asyncio.run`** — a sync→async bridge inside a synchronous transaction, rather
than an async route holding a sync connection. That is legal only because the
routes those services sit behind are sync `def` and therefore run on threadpool
threads, **and they must stay so**: making one of them `async def` would run
`asyncio.run` on a thread that already has a running loop, which raises. There is
one client and one `embed` call per write operation.

The cost is recorded in `search-and-retrieval.md` and it is real: **the SQLite
write lock is held across the provider round trip**, so concurrent writers wait.
**Flip condition:** if that wait becomes visible, the shape changes to
mark-stale-plus-rebuild, which was already the recorded runner-up.

Plan 006 shipped `llm_registry.py`'s two use-time validators with no call site at
all. **Both have callers now** — the chat validator through
`resolve_model_for_use` (plans 017, 021) and the embedding validator through the
embedding writes (plan 024) — so the "ships with no call site" note that stood
here is spent.

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
scoping is auditable in one layer.

**The four named selectables over `messages` are declared in the same module, and
they are Core expressions rather than SQL views** (`data-model.md`):
`settled_entries`, `current_zone`, `message_states` and `buried_messages`. They
execute no DDL, which is the point — bootstrap's `create_all` and the drift
page's `Create` / `Sync` handle tables only, drift and `/api/health` walk
`metadata.tables`, a Sync batch-recreate of `messages` would break a real view at
the rename step, and nothing in the product creates a view on an already-running
instance. **There are no SQL views anywhere in this schema**, and the phrase "the
two views" that this doc used to carry describes objects plan 012 deliberately
did not build. Every reader goes through a selectable; `services/settle.py` is
the only writer of the burial and settle columns.

### The connection, the engine factory, and the two write paths that deviate

Two paths deviate from "the request's own connection, one transaction per
service operation", and both are named so neither is read as a pattern:

- **The streaming harness writes a partial assistant row on its own short-lived
  connection** from `get_engine(settings)`, never the request-scoped
  `get_connection`, because `get_connection`'s teardown relative to body
  iteration is unverified for the installed FastAPI (019 D7, `session-stream.md`).
- **The tool seam dispatches on its own short-lived connection** and leaves no
  transaction open (021 D6, `session-stream.md`).

Two further deviations are in the persistence layer itself and are recorded
below: a FEAT-005 Sync rebuild is the **one** path that suspends
`PRAGMA foreign_keys`, and the whole-database import is the **one** path that
drops the `vec0` tables (`transfer.md`). The import's own self-reference problem
is solved by **insert-then-`UPDATE`**, deliberately **not** by deferring foreign
keys or toggling the pragma — widening that suspension to a second path would
make it look routine, which is exactly how it stops being checked.

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

**The derived tables live outside the registry, and that is a sixth fact**
(plan 024). The `vec0` and FTS5 virtual tables are declared in
`db/search_tables.py`, **not** in `metadata`, and are **ensured on write** —
created, if absent, inside the transaction of the write that needs them, at the
designated model's `embedding_dim`. They are outside `metadata` because their
dimension is not a static property of the schema: it is measured when an
administrator designates an embedding model (`data-model.md`), so a `Table`
literal could not declare it. **This is not startup DDL**, so fact 2's "no DDL at
startup" is untouched — `main.py`'s lifespan still runs none.

**A risk that follows, and it has no owner in the code today.** A Sync rebuild of
`memos` or `messages` is a create-copy-drop-rename, and the drop takes that
table's **FTS triggers** with it. The next ensure-on-write restores the triggers,
but it does **not** back-fill an already-existing FTS table — so between the Sync
and the next full rebuild, that lexical index is **stale** for every row written
in between. `fast/002.vector-index-rebuild` rebuilding both FTS tables is the
only repair, which makes rebuild-after-Sync an operational step rather than an
optional tidy-up (`admin-surfaces.md`).

The flip condition is recorded in `overview.md`.

### The two transaction rules, and the asymmetry between them

**The relational write, the composition read, the embed call and the vector write
all happen inside one transaction** (plan 024). The embed goes out through the
`asyncio.run` bridge above, from inside that block — which is what holds the
SQLite write lock across a provider round trip, the cost recorded under "The
first async code".

**A memo write and its embedding write are one transaction, and a failed
embedding fails the whole transaction.** That is the property the `sqlite-vec`
choice was made for: a service that commits the row and then embeds in a
follow-up transaction reintroduces exactly the drift the choice avoided.

**Message and session writes do the opposite, deliberately.** US-112 is explicit:
whatever stops an embedding being produced, an edit to a settled entry **still
saves**, and the roleplayer is told search coverage is incomplete (UC-078's
exception flow). The two postures, as built:

| Write | Embedding unavailable |
|---|---|
| memo create / memo **body** edit | **fails the transaction** — nothing is stored |
| memo body sent but **unchanged** | nothing — no model is needed |
| memo body edited to **blank** | the vector row is removed; no model is needed |
| memo **delete** | its `memo_vec` and `memo_fts` rows go in the same transaction; no model is needed |
| character **persona** edit, setup **description** edit (the `session_vec` fan-out) | **fails the transaction** |
| character / setup **create**, or a **name-only** edit | nothing — no session text changed, so no model is needed |
| settled-entry edit, settle, re-open, **partner filing** (`session_vec`) | **succeeds, degraded** — the row is stored and the response carries `search_coverage_incomplete` |
| zone append, zone-row edit | nothing — a zone row is not indexed; the coverage flag is false |

**The caught set on the degraded path is `no_embedding_model` (including the
dimension-mismatch form) and `llm_unreachable`** (024 U3, D8). The strict path
catches neither and lets both propagate, at 409 and 502 respectively. So
**`no_embedding_model` has two callers** — one that lets it out of the
transaction, one that swallows it and reports degradation in the write's own
response — and that split is the whole of the asymmetry's implementation.

**This asymmetry is deliberate and is named here so nobody harmonises the two
later.** In short: a memo exists *in order to be retrieved*, so an unembedded one
is a note that silently does nothing; a settled entry is *the record of what
happened*, and an instance-level omission must not block a roleplayer's own
record-keeping. The full reasoning is in `search-and-retrieval.md`, which owns
the embedding lifecycle and carries the same table; `session-stream.md` holds the
route-level view of the degraded path.

**One qualifier on the memo rule, added by the import** (plan 031). The strict
transaction is what makes a memo with no vector an **anomaly** — but **no import
embeds anything**, at any granularity, so after plan 031 a memo without a vector
is also a perfectly **normal post-import state**, until
`fast/002.vector-index-rebuild` runs. The transaction rule is unchanged for every
write that goes through the API; what changed is that "no vector" is no longer
diagnostic on its own (`transfer.md`).

**Two defects live on the degraded path**, recorded here because this is the
section a reader checks before changing it, and neither is behaviour this doc
endorses:

- **`secret_ref_missing` is not in the caught set — defect D-03.** An unset
  `$ENV_VAR` key on the designated server therefore makes a settle or a settled
  edit fail with a **500** and refuses the roleplayer's own text.
  `US-112.AC-1` was widened at the 2026-10-06 product finalization to cover
  "credentials the instance cannot use", so the build does not satisfy it. See
  `docs/plans/defects.md` D-03.
- **A failed degraded embed leaves any existing vector stale — defect D-04.**
  There is no staleness marker and no staleness column (024 U5), and the recorded
  remedy is the whole-index rebuild (UC-016). `US-112.AC-3`, new at the same
  finalization, requires the material's existing vectors to be **cleared**
  instead. See `docs/plans/defects.md` D-04, and note plan 032's finding that any
  such delete must resolve its row ids through an owner-scoped query first —
  the derived tables carry no user column.
