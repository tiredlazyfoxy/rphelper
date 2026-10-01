# Feature 001 — backend-foundation · intended documentation changes

Written by the planner before implementation; applied by `/architect` at finalization.
Entries are grouped by target architecture file. Nothing here is a product-layer change
— this feature delivers no product ids and cites none.

Several entries close a gap the architecture explicitly left open, and several record a
**planner inference** — a decision the docs do not state and a plan had to take. The
inferences are marked, because an inference that goes into the docs unmarked becomes
indistinguishable from a designed decision.

---

## `docs/architecture/backend-structure.md`

### § Database access — the PRAGMA and WAL lifecycle

**Change.** State that both PRAGMAs are applied by a **single SQLAlchemy `connect` event
listener on the engine**, running on every new connection, and that neither is applied
per transaction. Record that `PRAGMA foreign_keys = ON` genuinely is per-connection and
must be re-set every time, while `PRAGMA journal_mode = WAL` is a persistent file-level
property whose re-assertion is a cheap idempotent no-op — so there is one mechanism and
no first-open special case.

**Reason.** `brief.md`'s first open question. The doc said "on every connection" without
saying *how*, and the obvious alternative (WAL once at first open) would have been a
second mechanism with its own ordering question for a statement that costs nothing when
it is a no-op.

### § Database access — pooling, threading and the engine cache

**Change.** Add a short paragraph: one `Engine` per resolved database path, cached in
`db/engine.py`, using the pysqlite dialect's default pool for a file database with the
DBAPI same-thread assertion disabled, plus a disposal entry point for teardown.

**Reason.** Unaddressed by the docs, and a plan cannot avoid choosing. uvicorn hands a
pooled connection to whichever worker thread runs the request; the pool already
guarantees one connection is never used by two threads at once, so the same-thread
assertion forbids the normal case while protecting against nothing. Keying the cache on
the path rather than on a module singleton is what lets per-test databases coexist in
one process.

### § Database access — the `get_connection` dependency

**Change.** Name `get_connection` as the single, request-scoped way a router obtains a
Core `Connection`, declared in `db/engine.py`. State that it opens no transaction —
transaction boundaries stay `with conn.begin():` blocks at the service's own level.

**Reason.** The doc describes a connection factory but names no call-site mechanism.
Making the dependency the documented one is what keeps connection lifetime out of
handler code.

### § Database access — a failed `sqlite-vec` load fails loudly

**Change.** Record the posture: a connection on which the extension cannot be loaded
raises a dedicated operational exception rather than being handed out without the
extension. Record the version pin in `pyproject.toml`.

**Reason.** The extension is a hard requirement from stage `004` onward. A silently
missing extension surfaces much later as an inexplicable query error, in a feature that
did nothing wrong. The docs give no pin, so the pin is a decision rather than a
transcription.

### § Persistence access — the registry's concrete shape

**Change.** State it concretely: **one module-level `metadata = MetaData()` in
`db/schema.py`**, with every table declared as a `Table(...)` literal in that same file.
No per-feature table modules, no import-side-effect registration, no `build_registry()`
callable. `007` walks `metadata.tables`.

**Reason.** `brief.md`'s second open question. The root `CLAUDE.md` already says
`db/schema.py` *is* the source of truth; a single file has no import-order hazard, and
nothing can be silently absent from the drift report because it was never imported. In
this feature the file ships with the `MetaData` and zero tables.

### § The error model — `http_status` and the absent per-code table

**Change.** Record that `http_status` is a **class attribute each subclass sets**,
decided by the feature that introduces the code, and note explicitly that the twelve-row
table carries no status column by design rather than by omission. Add
`secret_ref_missing → 500` as the first row of whatever per-code status record the
architect prefers, with its reasoning: the caller cannot fix it by changing the request,
only by changing the environment and restarting.

**Reason.** A genuine gap. Twelve codes with no statuses would otherwise be decided
twelve separate times with no recorded rule.

### § The error model — handler registration (**planner inference**)

**Change.** Record the registration call site: an entry point in `errors.py` installs
the one handler for the base class on the application, and the app factory calls it.
Mark it as originating from this plan.

**Reason.** The doc says "one base class, one wire shape, one handler" and gives the
wire JSON, but contains no `@app.exception_handler` snippet and names no call site.
Recording it stops it being re-inferred, possibly differently, by the next feature that
adds a code.

### § The id generator — sequence exhaustion and the clock seam (**planner inference**)

**Change.** Record two things the doc does not cover: more than 4096 ids in one
millisecond **blocks until the next millisecond** (wrapping mints a duplicate; raising
turns a write burst into an error the caller cannot act on), and the generator reads
time through an injectable clock so drift and exhaustion are testable. Also state
explicitly that the backwards-clock exception is **not** a `DomainError` subclass — the
doc classifies it as a 500 operational fault, and the non-relationship is the kind of
thing someone later "tidies" into the hierarchy.

**Reason.** All three are silent-failure territory: a duplicate id, an untestable
refusal, and an operational fault dressed as a domain failure the SPA is told to render.

### § `/api/health` — behaviour, roll-up and status codes

**Change.** Record four things:

1. Against an **empty registry** `schema` is `"ok"`, and that is correct rather than a
   stub — the probe answers "is every declared table present?", and with nothing
   declared the answer is yes.
2. The roll-up precedence: a non-`"ok"` schema gives `"degraded"`; otherwise
   `configured` false gives `"unconfigured"`; otherwise `"ok"`.
3. **All three `status` values answer HTTP 200** (**planner inference**); a probe that
   cannot read the database at all is a 500. Reason: the body is the answer and all
   three consumers must read it, so returning `"degraded"` as a 503 would make the SPA
   discard the very body that explains the condition.
4. `"drift"` is a permitted value nothing produces until `007`, and `configured` is
   sharpened by `003` — both are widenings of the same function, not rewrites.

**Reason.** The doc gives the response shape and the intent but no status codes, no
roll-up rule and no answer for the pre-table state, which is the state the system is
actually in for the whole of stage 001.

### § Routers versus services — `services/health.py` (**planner inference**)

**Change.** Add `services/health.py` to the layout and note that it is **not a domain
service**: it enforces no rule from `domain-rules.md` and takes no `user_id`. It exists
because the probe issues SQL and the split forbids a router from doing so.

**Reason.** The doc's services list does not name it, and a reader finding it will
otherwise assume the split has a domain-shaped exception. It is the opposite — it is the
split being applied to its first router.

---

## `docs/architecture/quick-reference.md`

### Backend toolchain and packaging

**Change.** Add the convention: one PEP 621 `backend/pyproject.toml` holding runtime
deps, dev deps and the `[tool.ruff]` / `[tool.mypy]` / `[tool.pytest.ini_options]`
config; virtualenv at `backend/.venv` via `uv venv`; dependencies installed with
`uv sync`; `uv.lock` committed. No `requirements.txt` and no separate tool config files.
Minimum Python 3.12.

**Reason.** Every later backend feature adds a dependency and must know where it goes
and what regenerates the lock. Commands themselves stay in the root `CLAUDE.md` and are
not duplicated here.

### Backend test conventions

**Change.** Add two lines: the database fixture is a real `.sqlite` file under
pytest's `tmp_path`, **one per test**, obtained through the same engine factory
production uses; and environment isolation clears `RPHELPER_*` variables and the
settings accessor's cache around each test.

**Reason.** `:memory:` would make WAL a no-op and take a different extension-load path,
so it would silently not test the two properties `db/engine.py` exists to guarantee. A
shared session-scoped database leaks DDL state between tests, which is precisely what
`007` will be doing. Recording it keeps the next feature from re-deciding it cheaply.

### The `sqlite-vec` pin

**Change.** Record the pinned version alongside the stack facts.

**Reason.** The extension's availability is a hard runtime requirement and the docs name
no version.

---

## `docs/architecture/overview.md`

### Stack decision list

**Change.** Add uv as the backend package and environment manager, with the reason: a
committed lock is the only way the container build and a developer machine resolve the
same tree.

**Reason.** It is a stack choice made by this plan, and the stack decision list is where
a reader looks for one.

---

## `docs/architecture/deployment.md`

### Container build

**Change.** One line: the image installs backend dependencies from the committed
`backend/uv.lock` rather than resolving at build time.

**Reason.** A consequence of the packaging decision above, landing in the doc that owns
the build. Flagged as a forward-looking note — nothing in this feature builds an image.

---

_Nothing below this line is written by the planner._

---
Status: Applied 2026-10-01 — /architect finalization (with /product-spec finalization the same day)
Applied items: 15 (all entries; planner inferences kept as "(decided in plan 001)")
Rejected items: 0
Notes: applied in batch 1, except the `secret_ref_missing → 500` status posture, held as H1 and applied in batch 3 — 500 kept by user decision and recorded once as a shared posture with `schema_apply_failed` in `backend-structure.md`'s error model. The health entry's "`drift` produced by nothing until 007" is written as now produced by 007.
