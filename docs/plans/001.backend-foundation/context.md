# Feature 001 — Backend foundation · feature-wide context

## What this feature is

Stands the FastAPI application up as an empty but complete skeleton. The agreed
boundary is `brief.md` in this folder — its Definition and its Scope In/Out lists
bound every step here and are not restated. Read it first.

The four conventions this feature freezes, which no later feature may re-decide:
the snowflake id generator, the "int inside / decimal string on the wire" id rule,
the typed error hierarchy, and the table-definition registry.

## Product ids

**This feature delivers none.** `brief.md` records `Delivers: —`. No Definition-of-done
item in any step cites a `FEAT-###`, `UC-###` or `US-###.AC-#`, and none may be
invented to fill the gap. The `[test]` criteria here are structural and behavioural
and stand in their own terms.

## Greenfield — there is no existing code

`backend/` and `frontend/` do not exist. Only `docs/` and the root `CLAUDE.md` are
tracked. Every file named in every step's **Source files** list is a new file.
Nothing in this plan is a modification of anything, and no step may assume a helper,
a fixture or an import that an earlier step in this same feature did not create.

## Commands

From the root `CLAUDE.md`, run from `backend/`:

```
test       .venv/Scripts/python -m pytest
typecheck  .venv/Scripts/python -m mypy app
lint       .venv/Scripts/python -m ruff check .
```

The virtualenv at `backend/.venv` is created with `uv venv` and populated with
`uv sync`. The standalone uv is at `C:/Users/serge/.local/bin/uv.exe`.

## Architecture this binds to

- `docs/architecture/backend-structure.md` — Layout, Configuration, the logging call
  site, the `"$ENV_VAR"` secret-pointer pattern, the error model, the JSON id
  boundary, the id generator, routers versus services, Database access,
  Persistence access, `/api/health`.
- `docs/architecture/data-model.md` — Identifiers (the bit layout, the epoch, the
  backwards-clock rule, the storage rule), Schema drift and rebuild.
- `docs/architecture/deployment.md` — the logging posture and the redaction rule.

Cited, never copied. Where a step needs an exact declaration the architecture already
gives verbatim (the `Settings` block, the two snowflake aliases, `DomainError`,
`resolve_secret`'s contract), the step context points at the doc section and the
skeleton agent reproduces it — this plan does not restate signatures.

## The layout every step writes into

```
backend/
  pyproject.toml        # PEP 621: deps, dev deps, ruff/mypy/pytest config — one file
  uv.lock               # committed, generated, never hand-edited
  app/
    main.py             # app factory, router registration, lifespan
    config.py           # Settings + lru_cache accessor
    logging.py          # loguru sinks + InterceptHandler; called ONCE from main.py
    ids.py              # snowflake generator (NOT services/, NOT db/)
    secrets.py          # "$ENV_VAR" resolution
    errors.py           # typed error hierarchy + the one handler
    db/
      engine.py         # engine, connect listener, PRAGMAs, sqlite-vec, get_connection
      schema.py         # the registry: one MetaData, zero tables in this feature
    routers/
      health.py         # GET /api/health — the only router in scope
    services/
      health.py         # the health probe (see "services/health.py" below)
    models/
      ids.py            # SnowflakeIn / SnowflakeOut
      health.py         # the health response model
  tests/
```

`db/drift.py`, `db/sync.py`, `alembic.ini`, an `env.py` and a `versions/` directory
are **out of scope and must not be created** — they belong to feature `007`, and
Alembic is not even a dependency of this feature.

## Cross-cutting constraints every step holds

**Routers versus services is enforced from the first router.** A router owns path,
method, request/response models, auth dependencies, status codes and the translation
of a typed domain error to an HTTP response; it **contains no business rule and issues
no SQL**. A service takes plain arguments, returns plain results or raises a typed
error, and **never imports `fastapi`, never sees a `Request` and never knows a status
code**. Dependency direction is one-way: `routers → services → db`. `services` never
imports `routers`. `models/` is imported by both and imports neither.

**The JSON id boundary.** An id is an `int` in SQLite and Python and a **decimal
string** in every JSON payload — request bodies, response bodies, `DomainError.detail`
and SSE frames alike. `models/` is the only place the conversion happens. A route that
returns a plain `dict` or `JSONResponse` bypasses `models/` and therefore bypasses the
rule; routes return pydantic models. A bare `int` id field on a pydantic model is the
defect.

**The absolute redaction rule** (`deployment.md`), a prohibition with no level
exception, applying even at `DEBUG`. Never logged: message text (settled, buried or
current-zone), memo bodies, character persona/sheet text, setup text, session titles
and partner labels, translations, LLM prompt payloads, LLM completions, API keys and
resolved secret values. Allowed and sufficient: snowflake ids as decimal strings, error
codes from the typed error table, model references and tool names, token counts, row
counts, durations, HTTP status. In this feature the rule binds `errors.py`'s handler
and `secrets.py` — `resolve_secret`'s failure logs the **variable name**, never the
resolved value.

**Backend is fully type-annotated.** `mypy app` is a gate, not advice.

**No DDL at startup.** `main.py`'s lifespan runs no schema creation and no upgrade.
Remediation is admin-triggered and belongs to `007`.

## Decisions — settled, with their reasoning

These are recorded here because later features inherit them and because a decision
with no recorded reason gets re-litigated.

**D1 — Packaging: one PEP 621 `backend/pyproject.toml`, uv, committed lock.**
Runtime deps, dev deps and the `[tool.ruff]` / `[tool.mypy]` / `[tool.pytest.ini_options]`
configuration all live in that one file. The virtualenv is `backend/.venv`, created
with `uv venv` and populated with `uv sync`; `uv.lock` is committed so the container
build is reproducible. No `requirements.txt`, no separate `ruff.toml` / `mypy.ini` /
`pytest.ini`. Reason: one file is one place to look, and a committed lock is the only
way a container build and a developer machine resolve the same tree.

**D2 — Registry shape: one module-level `metadata = MetaData()` in `db/schema.py`.**
Every future table is declared as a `Table(...)` literal **in that same file**; `007`
walks `metadata.tables`. No per-feature table modules, no import-side-effect
registration, no `build_registry()` callable. Reason: the root `CLAUDE.md` says
`db/schema.py` *is* the source of truth; a single file has no import-order hazard, and
nothing can be silently absent from the drift report because it was never imported. In
this feature the file ships with the `MetaData` and **zero** `Table` objects.

**D3 — `/api/health` does a real probe and answers honestly.** Not stubbed constants.
It performs the cheap `sqlite_master` read and reports what actually exists:
`configured=false` while no `users` table holds an administrator, `schema="missing"`
when the database file or a declared registry table is absent, `"ok"` when every
registry table is present. Against an empty registry that is trivially `"ok"` — which
is **correct, not a stub**. `003` (accounts) and `007` (drift) later sharpen the same
function; the internals are designed so that is a widening, not a rewrite.

**D4 — Test database: a real `.sqlite` file under `tmp_path`, per test, through the
production engine factory.** Not `:memory:` — WAL is a no-op there and the extension
load takes a different path, so an in-memory database would exercise neither of the two
things the engine step exists to guarantee. Not a shared session-scoped database — DDL
state leaks between tests, which is exactly what `007` will be doing.

**D5 — PRAGMAs and WAL are set on every connection, by one `connect` event listener.**
`PRAGMA foreign_keys = ON` genuinely is per-connection and must be re-set every time.
`PRAGMA journal_mode = WAL` is a persistent file-level property, so re-asserting it on
each connection is a cheap idempotent no-op rather than a second mechanism — one
listener, no first-open special case, nothing per-transaction. This closes the first of
`brief.md`'s two open questions.

**D6 — Connection access is a `get_connection()` FastAPI dependency** yielding a
SQLAlchemy Core `Connection`, declared in `db/engine.py`. `/api/health` consumes it.
Reason: the dependency is the one place a connection's lifetime is bound to a request,
so no handler has to remember to close one.

**D7 — `http_status` is a class attribute each `DomainError` subclass sets.** The
architecture gives the field but no per-code status table, so the mapping lives with
the subclass that owns the code. This feature defines the base class, the single
handler, and **only `SecretRefError`**; the other eleven codes arrive with their own
features. The exception-handler *registration* is a planner inference from "one base
class, one wire shape, one handler" — the docs give no literal `@app.exception_handler`
snippet, and `outcome.md` asks the architect to record the inference.

**D8 — A `sqlite-vec` load failure fails loudly at connection time**, rather than
degrading to a connection without the extension. The extension is a hard requirement
from stage `004` onward, and a silently missing one surfaces as an inexplicable query
error much later, in a feature that did nothing wrong. `sqlite-vec` is version-pinned
in `pyproject.toml`; the docs give no pin, so the pin is a decision recorded in
`outcome.md`.

**D9 — Engine pooling and threading** (unaddressed by the docs, so the plan chooses).
One `Engine` per resolved database path, cached in `db/engine.py`, using the pysqlite
dialect's default pool for a file database, with `check_same_thread=False`. Reason:
uvicorn serves requests on a thread pool and hands a pooled connection to whichever
worker thread runs the request; the pool guarantees one connection is never used by two
threads at once, so disabling the same-thread assertion is safe and is what makes the
pool usable at all. A cache keyed on the path rather than a module singleton is what
lets D4's per-test databases coexist in one process. A `dispose_engines()` entry point
exists for fixture teardown.

**D10 — `services/health.py` exists, and it is not a domain service.** The health probe
issues SQL, and the routers/services split this feature is establishing forbids a router
from issuing SQL. So the probe is a service by construction, not by domain
classification. `brief.md`'s "no domain router or service" exclusion is untouched:
nothing here enforces a rule from `domain-rules.md` or takes a `user_id`. Recorded as a
planner inference in `outcome.md` because `backend-structure.md`'s services list does
not name it.

## Deviations from the orchestrator's suggested decomposition

Two, both forced by dependency direction or by the size budget:

1. **`secrets.py` moves out of the scaffold step and joins the errors step.**
   `resolve_secret` raises `SecretRefError`, which `errors.py` defines. Planning it into
   step `001` would have made step `001` depend on step `003`.
2. **`models/` merges into the ids step.** The two snowflake aliases are roughly fifteen
   lines of source — well under the 50-line floor — and the id and its wire form are one
   subject (`brief.md` names them as two of the four conventions in the same breath).
   Dependency direction allows the merge; a separate step would have been a step for
   two type aliases.

Net: six steps, not seven. The ordering constraint the orchestrator named still holds —
the scaffold comes first, and the app factory plus health comes last because health
integrates everything.

## Step map

| Step | Subject | Depends on |
|------|---------|------------|
| 001 | packaging, package skeleton, `Settings` + `get_settings` | — |
| 002 | `logging.py`: two sinks, `InterceptHandler` | 001 |
| 003 | `errors.py` + `secrets.py` | 001 |
| 004 | `ids.py` + `models/ids.py` (the JSON id boundary) | 001, 003 |
| 005 | `db/engine.py` + `db/schema.py` | 001 |
| 006 | `main.py` + `routers/health.py` + `services/health.py` + `models/health.py` | 001–005 |

## Test conventions later features inherit

- Tests live under `backend/tests/`; `backend/tests/conftest.py` holds the shared
  fixtures. It is created in step `001` and extended in step `005`, deliberately — the
  temp-file database fixture cannot land before `db/engine.py` exists.
- Environment isolation: a fixture clears every `RPHELPER_*` variable and clears
  `get_settings`'s `lru_cache` around each test, so no test observes another's
  configuration. Settings are overridden through the cache or through
  `dependency_overrides`, never by monkey-patching a module global.
- The database fixture is D4: a real file under `tmp_path`, one per test, obtained
  through the same engine factory production uses.
