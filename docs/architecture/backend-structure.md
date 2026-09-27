# Backend structure

**Realizes:** FEAT-001, FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-013,
FEAT-019, UC-003, UC-012, UC-013, UC-050, UC-065, UC-066

FastAPI application layout, the routers/services split, configuration and
secrets, and the error model that carries typed failures to the SPA. Commands
(`pytest`, `mypy app`, `ruff check .`) are in the root `CLAUDE.md`.

## Layout

```
backend/
  .venv/
  app/
    main.py              # app factory, router registration, lifespan
    config.py            # pydantic-settings Settings + lru_cache accessor
    secrets.py           # "$ENV_VAR" pointer resolution
    errors.py            # typed error hierarchy + exception handlers
    db/
      engine.py          # connection, PRAGMAs, sqlite-vec extension load
      schema.py          # the table-definition registry (data-model.md)
      drift.py           # PRAGMA introspection vs the registry (FEAT-005)
    routers/
      health.py          # /api/health
      bootstrap.py       # FEAT-001
      auth.py            # FEAT-002
      admin_users.py     # FEAT-003
      admin_llm.py       # FEAT-004
      admin_db.py        # FEAT-005
      characters.py      # FEAT-006
      setups.py          # FEAT-007
      sessions.py        # FEAT-008, FEAT-013
      entries.py         # FEAT-009, FEAT-011
      discussions.py     # FEAT-010  (SSE lives here)
      memos.py           # FEAT-012
      search.py          # FEAT-017
      transfer.py        # FEAT-018
    services/
      bootstrap.py  auth.py  users.py
      llm_registry.py            # servers, models, enabled-model validation
      config_resolver.py         # R1's two chains
      memo_chain.py              # R2
      characters.py  setups.py  sessions.py  entries.py
      discussion.py              # the compose loop, orchestrates llm + tools
      translation.py             # FEAT-011
      search/
        ports.py                 # the narrow search port (search-and-retrieval.md)
        hybrid.py                # vec + FTS + RRF
        memo_search.py  session_search.py  my_search.py
      llm/
        client.py                # one OpenAI-compatible client
        stream.py                # SSE frame emission
        tools.py                 # the three tool definitions + dispatch
      transfer.py                # export/import
    models/                      # pydantic request/response models
  tests/
```

## Routers versus services — the split, and why it is strict

**Routers** own HTTP and nothing else: path and method, request/response pydantic
models, authentication and authorization dependencies, status codes, and turning a
typed domain error into an HTTP response. A router contains no business rule and
issues no SQL.

**Services** own domain rules and data access. A service takes plain
arguments and returns plain results or raises a typed error; it never imports
`fastapi`, never sees a `Request`, and never knows a status code.

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
the session cookie and compares their role against the numeric ladder recorded in
`domain-rules.md`:

```python
ROLE_LADDER: dict[Role, int] = {Role.roleplayer: 0, Role.admin: 1}

def require_role(min_role: Role) -> Callable[..., CurrentUser]: ...
```

A factory rather than one `require_admin` dependency because the check every route
wants to express is a **threshold** — "at least this rung" — so a new rung is one
ladder entry rather than a new dependency per role plus an audit of which routes
should have gained it. It replaces what an earlier draft of this doc called
`require_admin` and what the sibling project spelt as a `{author, admin}` ladder.

`require_role(Role.admin)` sits on **every** route in `admin_users.py`,
`admin_llm.py` and `admin_db.py` — as a router-level dependency, not per handler,
so adding an admin route cannot forget it. The frontend's pre-mount gate
(`admin-surfaces.md`) is UX only; this is the boundary. Every route behind it is
additionally bound by R5: it returns no user content and no count derived from it.

`require_user` yields the `user_id` that every service call is scoped by. A
service that touches user-owned data takes `user_id` as a **required positional
argument** — not an optional filter, not a keyword with a default. A forgotten
scope becomes a type error rather than a privacy incident.

`require_unconfigured` implements UC-003 directly: once the instance is
configured, every bootstrap route refuses (create-new and import alike) and the
client is directed to sign in. The check is a dependency rather than a check
inside each handler so that adding a bootstrap route cannot forget it.

## Configuration — `pydantic-settings`

One `Settings` model in `app/config.py`, with **`RPHELPER_<FIELD>` validation
aliases**:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Field(default=Path("data"), validation_alias="RPHELPER_DATA_DIR")
    db_filename: str = Field(default="rphelper.sqlite", validation_alias="RPHELPER_DB_FILENAME")
    session_cookie_name: str = Field(default="rphelper_session", validation_alias="RPHELPER_SESSION_COOKIE_NAME")
    session_ttl_hours: int = Field(default=720, validation_alias="RPHELPER_SESSION_TTL_HOURS")
    # ... one field per setting, each with an explicit RPHELPER_ alias

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- **Explicit `RPHELPER_` validation aliases** rather than an `env_prefix`, because
  an explicit alias per field makes the full environment contract greppable and
  keeps a field rename from silently renaming an operator-facing variable.
- **`lru_cache` singleton** so settings are parsed and validated once at first use;
  routers depend on `get_settings` so tests can override the cache rather than
  monkey-patching a module global.
- The env file is resolved **relative to the backend working directory**, matching
  the inherited convention and what `start.ps1` and the container both set.
- **Ports are not settings.** `8184` and `8193` are hardcoded literals in
  `start.ps1`, `vite.config.ts`, the Dockerfile and compose (`deployment.md`).
  Reason: they are topology, fixed by the sibling-project port allocation, and
  making them configurable would create a way for the Vite proxy target and the
  uvicorn bind to disagree.

## The `"$ENV_VAR"` secret-pointer pattern

**Realizes:** FEAT-004, FEAT-018, UC-010, UC-061

An LLM server's credential is **never stored in the database**. The
`llm_servers.api_key_ref` column holds a *pointer*: the literal string
`"$OPENAI_API_KEY"`, resolved from the process environment at call time.

```python
def resolve_secret(ref: str | None) -> str | None:
    """'$NAME' -> os.environ['NAME']; None -> None; anything else -> SecretRefError."""
```

Rules:

- A value that does not start with `$` is **rejected on write**, so a pasted raw
  key cannot be persisted by accident. The admin UI says what the field expects.
- Resolution happens **at call time**, not at registration time and not at
  startup, so rotating a key is an environment change plus a restart, with no
  database write and no re-registration.
- A missing environment variable is a **typed error** (`SecretRefError`) surfaced
  through the normal error model, not a `None` that turns into an
  unauthenticated request against the provider.

Why this is exactly right for RPHelper rather than merely inherited from
BookWriter: FEAT-018/UC-061 requires a whole-database export that an
administrator may move between instances, and FEAT-019 makes that export
deliberately opaque. A database holding credentials would turn every export into a
secret-bearing artifact and every drift report into something needing redaction.
With pointers, the export moves configuration and the environment supplies
credentials — stated in `data-model.md` as a visible operational consequence.

## The error model

**Realizes:** FEAT-004, FEAT-010, FEAT-011, FEAT-013, UC-012, UC-032, UC-039

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
| `model_not_enabled` | Use-time validation of a resolved model reference fails (R4) | the model reference, and **which level set it** (`user`/`character`/`session`) | FEAT-004, UC-012 |
| `no_embedding_model` | Semantic search or embedding is attempted with no designated embedding model, or the designation is gone (R4's second half) | nothing user-scoped | FEAT-004, UC-013 |
| `secret_ref_missing` | `"$ENV_VAR"` names an absent variable | the variable name | FEAT-004 |
| `llm_unreachable` | Provider call fails or times out | provider-side message, no request body | FEAT-010, UC-032 |
| `tool_failed` | A tool invocation fails — **not surfaced as a stream error** (R9) | tool name | FEAT-014, FEAT-015, FEAT-016 |
| `translation_failed` | UC-039's exception flow; nothing is cached | entry id | FEAT-011 |
| `discussion_not_resumable` | Re-open attempted once an entry follows the answer (UC-037) | discussion id | FEAT-010 |
| `already_configured` | A bootstrap route is reached on a configured instance (UC-003) | nothing | FEAT-001 |
| `account_disabled` | Login by a disabled account (FEAT-002) | nothing | FEAT-002 |

Two rules about `detail` that are privacy rules, not formatting preferences:

- **`detail` never contains another user's data**, and never contains counts
  derived from other users' data (R5). In particular `model_not_enabled` names the
  model and the level, never how many sessions are affected.
- **`detail` never contains memo body text for a `disabled` memo** — R3's "no path"
  includes error payloads.

`model_not_enabled` carrying *which level set the reference* is the one place the
error model does real product work: UC-012 says the roleplayer resolves the
situation "by choosing another model through FEAT-013's chain", and they can only
do that if they are told whether the dead reference came from their account
default, the character, or this session.

## Streaming endpoint shape

`discussions.py` owns the one streaming route. It returns a
`StreamingResponse(media_type="text/event-stream")` and sets
**`X-Accel-Buffering: no`** on that response (see `deployment.md` — the header is
emitted by the application, deliberately, rather than relying only on nginx's
`proxy_buffering off`). The request is a **POST with a JSON body**, which is the
reason the client is `fetch()` + `body.getReader()` rather than `EventSource`
(`overview.md`, `frontend-structure.md`).

The frame protocol and the tool loop are in `llm-and-streaming.md`. Two ordering
rules belong here because they are route-level:

1. **The roleplayer's message is committed before the stream opens** (R10). The
   handler writes the `discussion_messages` row, commits, and only then begins
   generation — so `llm_unreachable` cannot lose typed text.
2. **A domain error mid-stream becomes an `error` frame, not an HTTP status.** The
   status was already sent. The frame carries the same `{code, message, detail}`
   shape as the JSON error body so the SPA has one error renderer.

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
  bootstrap at all, and UC-003's refusal is the server-side enforcement of the
  same fact.
- **`schema`** is a coarse roll-up of FEAT-005's drift check (the detailed
  per-table report is admin-only, `admin_db.py`). It is safe unauthenticated
  because it names no table contents and no user.
- It is also the container healthcheck target (`deployment.md`). This matters
  because `supervisord` has no wait-for ordering: nginx can accept connections
  before uvicorn is listening, so the probe has to come from the app, not from
  nginx answering for it.

The endpoint deliberately **touches the database** (a cheap `sqlite_master` read)
rather than returning a static `{"status":"ok"}`. A health check that cannot fail
tells an operator nothing, and FEAT-001's whole problem is an instance that is
running but not usable.

## `GET /api/me`

**Realizes:** FEAT-002, FEAT-003, FEAT-019

Owned by `auth.py`. Returns the **caller's own identity** — the minimum an entry
needs to decide what to render:

```json
{ "id": 7, "username": "...", "role": "roleplayer" | "admin" }
```

It requires a live session and answers **401** when there is none, or when the
session's account no longer resolves — deleted, or disabled (FEAT-003). It carries
**nothing but the caller's own identity**: no counts, no other accounts, no
content. It is a read path scoped to `require_user`'s `user_id`, which is the
whole of its scope.

Two consumers, and the first is why it exists:

- **The `admin` entry awaits it before mounting** (`admin-surfaces.md`). RPHelper
  cannot decode a role client-side — the session is an HttpOnly cookie — and
  FEAT-003's "disabling an account ends that user's sessions" requires a
  server-side check anyway, because a stateless token cannot be revoked. So the
  admin gate is one round-trip to this route, and the entry renders nothing until
  it answers.
- The `app` entry uses it for the header's user menu and sign-out affordance.

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

**The second route is a deliberate deviation from the sibling project**, which has
no separate test endpoint and tests a connection by reusing the model listing.
Reason: FEAT-004's purpose line treats testing a connection as its **own
capability**, and overloading the model-listing call conflates two questions —
"can I reach and authenticate against this server" and "what can it run". A UI
that must open a model picker to learn that a base URL is wrong is answering the
first question as a side effect of the second. Reusing the *primitive* while
splitting the *route* keeps one implementation and two honest contracts.

The test route writes `llm_servers.last_test_at` / `last_test_ok` /
`last_test_error` (`data-model.md`), and per UC-011 a failed test **never** blocks
or removes a registration. Its result is a **typed value**, not a prose message
the SPA has to interpret; the proposed value set and its `_TBD:` are in
`admin-surfaces.md`.

## Database access

One SQLite connection factory in `db/engine.py`, which on every connection:

- sets `PRAGMA foreign_keys = ON`,
- sets `PRAGMA journal_mode = WAL` — readers do not block the single writer, which
  matters because an SSE-streaming discussion holds a request open while other
  reads happen,
- loads the `sqlite-vec` extension, so `vec0` tables and the KNN operators are
  available on every connection rather than only where someone remembered.

### Persistence access — SQLAlchemy **Core**, not the ORM

Decided. Data access goes through **SQLAlchemy Core** — `MetaData`, `Table`,
`select()`/`insert()`/`update()`, explicit `Connection` and `begin()`. The
**declarative ORM is not used**: no `DeclarativeBase`, no mapped classes, no
`Session`, no identity map, no lazy loading.

Three reasons, in the order they decided it:

1. **Explicit transaction scoping.** The R-rules require transactions the code can
   see. A memo write and its embedding write are **one transaction**
   (`search-and-retrieval.md`), and disabling an account flips `users.role`/
   `is_enabled` **and** revokes its `auth_sessions` rows atomically (FEAT-003,
   `data-model.md`). Core makes the transaction boundary a `with
   conn.begin():` block at the service's own level. The ORM's unit-of-work flushes
   when it decides to, which is exactly the wrong property for an invariant that
   is stated as "these two writes commit together or not at all".
2. **A `text()` escape hatch for the queries no ORM expresses.** `vec0 MATCH`
   with a bound query vector and `ORDER BY distance`, and FTS5 `MATCH` with
   `bm25()`, are SQLite-extension syntax with no expression-language equivalent.
   `search-and-retrieval.md`'s query shape — a relational CTE feeding two arms —
   has to be written as SQL. Core lets that be `text()` against the same
   connection and inside the same transaction as everything around it, instead of
   an ORM session plus a raw-connection side channel with two transaction stories.
3. **FEAT-005 needs a registry it can introspect, not mapped classes.** UC-014
   asks for the *current structural truth per table*, answered by `PRAGMA
   table_info` / `index_list` compared against a declaration
   (`data-model.md`). A Core `MetaData` with `Table` objects **is** that
   declaration — `db/schema.py` stays the single introspectable source of truth
   and `db/drift.py` walks it directly. Declarative models would put the same
   information behind a mapper layer whose job is object identity, not schema
   description, and the drift checker would end up reading `__table__` off classes
   that exist for no other reason.

What does **not** change: the registry in `db/schema.py` remains authoritative for
both the creation path and the drift report, and all SQL stays in `services`/`db`
(the router/service split above) so R5's query-level scoping is auditable in one
layer.

`_TBD: whether schema evolution is handled by migration files (Alembic or
hand-written) or by registry-only create-if-missing is NOT decided here. UC-015
asks that missing tables be created, which the registry answers on its own;
nothing in docs/product/ states what happens to an existing table whose shape
changed. FEAT-005's plan must choose, and the choice interacts with the Sync
action recorded as unrequired in admin-surfaces.md._`

Transaction rule that is load-bearing: **a memo write and its embedding write are
one transaction**, and likewise for a session summary. That is the property the
`sqlite-vec` choice was made for; a service that commits the row and then embeds
in a follow-up transaction reintroduces exactly the drift the choice avoided.
