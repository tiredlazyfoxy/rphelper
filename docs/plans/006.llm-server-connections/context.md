# Feature 006 — LLM server connections · feature-wide context

## What this feature is

Gives ACT-001 the page on which the instance learns which model servers exist and which
of their models may be used. A connection is a base URL plus a **pointer** to an
environment variable — never a stored credential. Testing a connection is its own action
with its own typed result and never blocks or removes a registration. Models a server
offers are individually enabled, and exactly one model across the whole instance is
designated for embeddings. Disabling a model is always allowed and never refused on
account of anybody's sessions; the consequence surfaces later, at use time, as a typed
error rather than a silent substitution.

The agreed boundary is `brief.md` in this folder — its Definition and its Scope In/Out
bound every step here and are **not** restated or widened. Read it first. Its two open
questions are closed by D4 and D5 below.

## Product ids

`FEAT-004`, via **UC-010**, **UC-011**, **UC-012**, **UC-013** and **US-012**, **US-013**,
**US-014**, **US-015**, **US-016**.

| Criterion | Where it lands |
|---|---|
| US-012.AC-1 (a chosen kind plus details is saved) | `003` (the service writes the row), `005` (the route), `007` (the form) |
| US-012.AC-2 (it appears in the connection list) | `003` (the list read), `005` (the list route), `006` (the rendered table) |
| US-013.AC-1 (a reachable connection is reported reachable) | `003` (the probe primitive and the recorded result), `005` (the test route), `006` (the badge) |
| US-013.AC-2 (a failure is reported and the connection stays registered) | `003`, `005`, `006` |
| US-014.AC-1 (an enabled model becomes selectable) | `004` (the registry half — see below), `008` |
| US-014.AC-2 (a disabled model stops being selectable) | `004`, `008` |
| US-015.AC-1 (a designation is saved) | `004` (the service, including the measured dimension), `005` (the route), `009` (the modal) |
| US-016.AC-1 (the disable is never refused on account of a dependency) | `004`, `008` |
| US-016.AC-2 (an error rather than a silent substitution on next use) | `004` (`model_not_enabled`, tested directly against the service — see D10) |

**US-014's "selectable when configuring a session" and US-016.AC-3 are only half
deliverable here, and the half that is not is FEAT-013's.** This feature owns the
registry — which models are enabled, and the use-time predicate over it. The session
configuration chain that *consumes* it (UC-050, FEAT-013) is feature `017`'s, and the
session surface that renders the error is `011`/`019`'s. Every `[test]` item below is
written against what this feature can actually observe: the registry's own answer. No id
is invented and no criterion is claimed to be fully covered when it is not.

**Related, cited but not delivered here:** UC-016 / FEAT-005 (the rebuild that a changed
embedding dimension would need — feature `007`'s), UC-051 / UC-053 / FEAT-014 / FEAT-015
(the semantic tools that consume the designation), UC-065 / UC-066 / FEAT-019 (the
cross-cutting privacy audit — feature `032`'s).

## Assumption every step rests on — what is built and what is only planned

`backend/` is built through **`001.backend-foundation`**; `frontend/` is built through
**`002.frontend-foundation`**, whose four `main.tsx` files are still placeholders.
Features **`003.first-run-bootstrap`**, **`004.authentication-session`** and
**`005.admin-shell-and-users`** are **planned, not built** — every row in their
`status.md` is `pending`. Build order is `001 → 002 → fast/001 → 003 → 004 → 005 → 006`.

**Built and quotable today** (this feature imports these as they stand):

| Module | What this feature uses |
|---|---|
| `backend/app/db/schema.py` | the one `metadata`; every table is a `Table(...)` literal **in this file**, PKs are `BigInteger` and never autoincrement |
| `backend/app/db/engine.py` | `get_connection` (opens **no** transaction), `get_engine`, the `foreign_keys`/`WAL`/`sqlite-vec` PRAGMAs |
| `backend/app/ids.py` | the generator, built once in `create_app()` and held on `app.state`; services receive it as an **explicit argument** |
| `backend/app/models/ids.py` | the outbound and inbound snowflake aliases |
| `backend/app/errors.py` | `DomainError`, `register_exception_handlers`, and `SecretRefError` (`secret_ref_missing`, 500) |
| `backend/app/secrets.py` | `resolve_secret` — **used unchanged**, read-time only |
| `backend/app/config.py` | `Settings` + `@lru_cache get_settings` |
| `frontend/src/shared/api.ts` | `apiGet` / `apiPost` / `apiPatch` / `apiDelete`, the `/api/` path rule, the 401 navigation |
| `frontend/src/shared/apiError.ts` | `ApiError` with `.code` / `.status` / `.detail`, `isApiError` |
| `frontend/src/shared/IconButton.tsx` | the only sanctioned icon-only control |
| `frontend/src/shared/AppProviders.tsx` | the Mantine + notifications wrapper |

**Arriving with `003`/`004`/`005`, named by role and module path and never quoted as an
exact signature:**

- `backend/app/roles.py` — the `Role` enum and the ladder (`003/001`, `004/002`).
- `backend/app/dependencies.py` — `require_role(min_role)`, the dependency **factory**
  (`004/002`). This feature attaches it once, at router level.
- `backend/app/routers/admin_users.py` + `backend/app/services/users.py` (`005/002`,
  `005/003`) — the **precedent** for an admin router: its own prefix under
  `/api/admin/`, `require_role(Role.admin)` on the router, one service call per handler.
- `frontend/src/admin/AdminApp.tsx` (`005/005`) — the flat four-route `<Routes>`;
  `/llm-servers` renders the 404 element until this feature replaces that one row.
- `frontend/src/shared/ConfirmModal.tsx` (`005/006`) — the one shared confirm dialog.
  `005` names this feature's delete-connection confirm as an intended reuse; **it is
  reused, never hand-rolled**.
- `frontend/src/admin/usersPageState.ts`, `UsersPage.tsx`, `createUserDraft.ts`,
  `CreateUserModal.tsx` (`005/006`–`008`) — the worked examples of the page-state and
  `*Draft.ts` shapes this feature mirrors.

**No step here quotes an exact signature for anything `003`, `004` or `005` delivers.**
Borrowed interfaces are named by role and module path; the skeleton agent resolves the
exact names against the delivered code. If the delivered code contradicts what a step
assumes, that is a **skeleton hand-back**, not something a coder improvises around.

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

- `docs/architecture/backend-structure.md` — Layout (`routers/admin_llm.py`,
  `services/llm_registry.py`, `services/llm/client.py`), the id generator, **the JSON id
  boundary**, routers-versus-services, "Authorization as router dependencies",
  Configuration, **the `"$ENV_VAR"` secret-pointer pattern**, the error model, **"The
  connection probe — one primitive, two routes"**, Database access.
- `docs/architecture/data-model.md` — `llm_servers`, `models`, Identifiers, and the
  Vector-tables section (which is what `models.embedding_dim` is *for*; no `vec0` table is
  created here).
- `docs/architecture/llm-and-streaming.md` — "One OpenAI-compatible client" and "The model
  registry and use-time validation" (lines 1–90 only; the SSE protocol and the compose
  loop belong to `019`/`021`).
- `docs/architecture/admin-surfaces.md` — "LLM Servers page — FEAT-004" in full, plus the
  shell and nav sections.
- `docs/architecture/ui-conventions.md` — tables; no sorting/filtering/pagination;
  loading, errors and empty states; create-and-edit-are-modals; **the MobX draft
  convention**; async feedback; mutations are never optimistic; **the confirm
  convention**; page state.
- `docs/architecture/domain-rules.md` — **R4** and **R5**.
- `docs/product/use-cases/FEAT-004.*.md`, `docs/product/stories/FEAT-004.*.md`.

Cited, never copied. Where a step needs a declaration an architecture doc gives verbatim
(the two column lists, the wire shape of a domain error, the probe taxonomy), the step's
context points at the section and the skeleton agent reproduces it.

## Files this feature touches

```
backend/
  pyproject.toml                    # httpx dev -> runtime                        (002)
  app/
    db/schema.py                    # + llm_servers, + models                     (001)
    errors.py                       # + 4 subclasses                              (001)
    config.py                       # + llm_request_timeout_seconds               (001)
    models/secret_ref.py            # NEW — the write-time "$ENV_VAR" field type  (001)
    services/llm/__init__.py        # NEW — package marker                        (002)
    services/llm/client.py          # NEW — the one OpenAI-compatible client      (002)
    services/llm_registry.py        # NEW — servers + the probe primitive         (003)
                                    # + models, designation, use-time validators  (004)
    models/admin_llm.py             # NEW — request/response models               (005)
    routers/admin_llm.py            # NEW — the guarded router                    (005)
    main.py                         # + one include_router line                   (005)
frontend/
  src/
    admin/AdminApp.tsx              # the /llm-servers route element replaced     (006)
    admin/llmServersPageState.ts    # NEW — the page store + its free functions   (006)
    admin/LlmServersPage.tsx        # NEW — the table and the row menu     (006,007,008,009)
    admin/serverFormDraft.ts        # NEW — draft, validation, submit             (007)
    admin/ServerFormModal.tsx       # NEW — create and edit                       (007)
    admin/modelPicker.ts            # NEW — the shared probe-on-open picker       (008)
    admin/enabledModelsDraft.ts     # NEW                                         (008)
    admin/EnabledModelsModal.tsx    # NEW                                         (008)
    admin/embeddingDraft.ts         # NEW                                         (009)
    admin/EmbeddingModal.tsx        # NEW                                         (009)
```

**Not touched, and a step that touches one is out of scope:** `frontend/vite.config.ts`
(no new entry, no new test setting), `frontend/src/admin/index.html`,
`frontend/src/admin/main.tsx`, `frontend/src/admin/AdminShell.tsx`,
`frontend/src/admin/navItems.ts` (`005` already declares the `LLM Servers` row),
`frontend/src/shared/*` (every shared module this feature needs already exists or arrives
with `005`), `frontend/src/global.css`, `frontend/src/shell.css`,
`frontend/tests/conventions.test.ts` (see "Cross-cutting constraints"),
`backend/app/secrets.py` (read-time resolution is complete and unchanged — D8),
`backend/app/db/drift.py`, `backend/app/db/sync.py` (feature `007`).

**Out of scope, per `brief.md`:** streaming completions (`019`), the compose loop
(`021`), embedding *generation* and the `vec0` tables (`024`), how a session resolves its
model (`017`). `chat_stream` is **not stubbed** on the client — see D3.

## Cross-cutting constraints every step holds

**R5 — the reverse lookup does not exist, in any form.** A `model → dependent sessions`
query must not exist as an endpoint, a count, a badge, a tooltip, a `detail` field or a
confirm sentence. The exact string **"Are you sure? N sessions use this model"** and every
variant is forbidden. `domain-rules.md` names *this page* as the site where it gets
written in good faith. Every confirm sentence in this feature describes **the action**,
never a blast radius. The `enabled-model count` column is a count of *models on this
server* — administrative data about a registration — and is the only count on the page.

**R4 — no silent fallback, ever.** Enabling and disabling models here is precisely what
makes use-time validation necessary. No code in this feature substitutes a model,
defaults to "the first enabled one", or clears a designation as a side effect of anything.

**The database never contains a credential.** `llm_servers.api_key_ref` holds the literal
text `"$NAME"`. It is **never returned by any route**; the wire carries a boolean
"has API key" and nothing more. A value not starting with `$` is rejected on write (D8).
Resolution is at call time through the existing `resolve_secret`, and a missing variable
is `secret_ref_missing` raised **before** any network call.

**`require_role(Role.admin)` sits on the router, not the handlers**, so a route added
later cannot forget it (`backend-structure.md`; the pattern `005/003` DoD-4 proves).

**Routers versus services stays strict.** The router owns path, method, models,
dependencies and status code, issues **no SQL** and holds no rule. The service takes plain
arguments, returns frozen dataclasses or raises a typed error, and **never imports
`fastapi`, never sees a `Request`, never knows a status code**. Direction is one-way:
`routers → services → db`. `Settings` and the snowflake generator reach a service as
plain arguments.

**Transaction boundaries are the service's own `with conn.begin():` blocks** — the
connection dependency opens none. Each atomic operation is one block. The designation
write (clear every other row, then upsert this one) is **one** block; the delete of a
server and its `models` rows is **one** block.

**The JSON id boundary.** Every id is an `int` in Python and SQLite and a **decimal
string** in every JSON body, every `detail` and every TypeScript type. Response models use
the outbound alias, request bodies and **path parameters** use the inbound one (`005`'s
D9). A bare `int` id field or a TypeScript `id: number` is the defect; there is no
`parseInt` and no numeric sort anywhere in this feature.

**No DDL at startup.** `main.py`'s lifespan still runs nothing; the two new tables reach a
fresh instance through the bootstrap `create_all` `003` owns. An instance bootstrapped
before `006` ships lacks both tables — that is drift, and feature `007`'s remediation.

**The admin area adds no stylesheet.** No `.css`, no `.module.css`, no style block under
`frontend/src/admin/`. `src/app/main.tsx` stays the only module importing `shell.css`.

**Failures render in place, so `notifyFailure` is called nowhere in this feature.** A page
failure is the inline `Alert` above the table; a modal failure is a field error or the
modal's general key. `002/006`'s scan — Mantine's notification API imported by
`shared/notifyFailure.ts` alone — stays true, and **no step touches
`frontend/tests/conventions.test.ts`**: its surviving clauses (no forbidden styling
mechanism; the notification-import scan) both hold unchanged, and its MobX-absence clause
was already deleted by `003/004` DoD-11.

**Mutations are never optimistic.** Every mutation is followed by a re-load of the list.
Handler invocations are `void`-ed with a non-rethrowing catch. **No success toasts** — the
modal closing and the list refreshing is the success signal.

**Frontend is TypeScript only.** No `.js`, `.jsx`, `.mjs` or `.cjs`; `tsc --noEmit` is the
only static gate.

**The redaction rule** (`deployment.md`) binds every log line: ids as decimal strings,
error codes, counts, statuses — **never a base URL's credential, never a resolved API key,
never a provider response body**.

## Decisions — settled, with their reasoning

### D1 — There is no "active" flag on a server

**User decision.** `admin-surfaces.md` puts an "active" switch on the server form and an
"active" badge column on the table. **Both are dropped.** `data-model.md`'s `llm_servers`
declares no such column, no UC and no US asks for one, and a planner may not edit the
table registry. The table's columns are therefore **name, backend-type badge, base URL,
has API key, enabled-model count**, plus the last-test badge D6 earns and the trailing
action column. `outcome.md` asks the architect to correct that section.

### D2 — Designating the embedding model measures `embedding_dim` with one real embeddings call

**User decision.** The dimension is a fixed property of the model and is **not
discoverable from a models listing** — neither provider kind returns dimension metadata.
So designation embeds one short fixed string against that server, measures the length of
the returned vector and writes it to `models.embedding_dim`. A failed call, or a response
carrying no usable vector, **blocks the designation** with a typed error, so the
administrator learns at pick time rather than at first search.

This is why `embed` exists on the client in this feature, and `024` reuses it. **It is the
only place `006` touches the embeddings endpoint**; generating and storing vectors, and
the `vec0` tables `embedding_dim` ultimately declares, remain `024`'s and `007`'s — the
brief's Out list still holds.

Per UC-013's postcondition a changed designation **neither forces nor prompts a rebuild**,
so nothing here warns about a dimension change and nothing offers one. The remedy is
UC-016, always available.

### D3 — `httpx` becomes a runtime dependency, and the client is async

This feature is the first outbound-HTTP code in `app/`. `httpx` moves from
`[dependency-groups] dev` in `backend/pyproject.toml` into the runtime `dependencies`,
keeping a compatible constraint; it stays available to `TestClient` exactly as before.
This is a deliberate `pyproject.toml` edit inside step `002`'s scope, not creep.

The client uses **`httpx.AsyncClient`**, because `019`/`021` stream server-sent events
through this same module and a sync client cannot do that without being rewritten. The
consequence, stated so it reads as decided rather than as an oversight: the three registry
functions that make an outbound call are `async def`, and so are their three routes, while
the SQLAlchemy `Connection` they hold stays **sync**. The small single-row reads and
writes around the network call block the event loop for microseconds on a WAL database;
the only slow part — the network — is awaited. `outcome.md` asks the architect to record
the mix and its flip condition.

**`chat_stream` is not written and not stubbed here.** A stub with no caller is dead code
that `019` would rewrite anyway.

### D4 — Use-time validation only; no cascade — the brief's first open question, closed

**User decision.** Designation is **independent** of `is_enabled`. Disabling a model
**never** refuses (UC-012, US-016.AC-1, R5) and **never** clears a designation. Validation
happens at **use** time and requires the model to be both **designated and enabled**;
otherwise `no_embedding_model`. This feature owns **no cross-table cascade** of any kind.

It mirrors R4's shape for chat models exactly: `model_not_enabled` is likewise a use-time
check with no substitution and no fallback.

### D5 — The probe is one primitive; `kind` is a label, never a dispatch key — the brief's second open question, closed

Both provider kinds speak the OpenAI wire format, so the probe issues **the same request
against both**: a models-listing `GET` against the server's base URL with the resolved
credential as a bearer token. `llm_servers.kind` is used for admin-facing presentation and
provider defaults only.

**There is no branch on `kind` anywhere in this feature** — not in the client, not in the
probe, not in the registry. `llm-and-streaming.md` states this outright. It is recorded
here because "two provider kinds" reads like it wants two code paths and it must not get
them; a second adapter would create two paths that must be kept behaviourally identical
with no compensating benefit.

The allowed values are constrained at the pydantic boundary as a two-member literal,
answered by FastAPI's own **422**, and the column is plain text with no `CHECK`. No domain
error code is invented for a bad kind.

### D6 — The four-value probe taxonomy stands

```
reachable | unreachable | auth_failed | model_list_empty
```

per `admin-surfaces.md`. UC-011's postcondition commits the product to reachable /
unreachable only and explicitly hands the finer distinction to design; the two extra
values are kept because the probe genuinely can distinguish them, and collapsing them
tells an administrator with a bad API key to check their base URL.

Mapping, fixed here so every layer agrees:

| Outcome | Condition | `last_test_ok` |
|---|---|---|
| `reachable` | 2xx and the listing names at least one model | true |
| `model_list_empty` | 2xx and the listing names none | false |
| `auth_failed` | 401 or 403 | false |
| `unreachable` | a transport failure, a timeout, or any other non-2xx | false |

`model_list_empty` is `ok = false` because `admin-surfaces.md` is explicit that both extra
values are *kinds of not-reachable*, so a consumer that understands only the product's two
is never wrong, only less specific.

The route returns a **typed value**, never free text the UI parses, and
`llm_servers.last_test_error` stores **the outcome value itself** — never a provider
message. A provider-side message is not persisted: the column feeds a badge, and storing
prose would invite the UI to parse it.

### D7 — HTTP statuses for the codes this feature introduces

`backend-structure.md` names three codes and assigns no status, deferring it to the
introducing feature. This feature fixes them, and adds a fourth the admin route surface
needs:

| `code` | Status | Why |
|---|---|---|
| `llm_unreachable` | **502** | the failure is upstream of this instance, not a fault in the caller's request |
| `no_embedding_model` | **409** | the instance's configuration conflicts with the attempted operation; nothing about the request is malformed |
| `model_not_enabled` | **409** | same shape — a configuration conflict, not a bad request and not an authorization failure |
| `llm_server_not_found` | **404** | mirrors `005`'s `user_not_found`; every id-addressed route needs one |

`llm_server_not_found` is **not** in `backend-structure.md`'s table; it is added here for
the same reason `005` added `user_not_found`, and `outcome.md` asks the architect to record
it. `secret_ref_missing` already exists at **500** and is reused **unchanged** — see D14
for the one place that hurts. Each of the four is a new `DomainError` subclass and nothing
more: **no new handler is ever registered**.

### D8 — `api_key_ref` write-time validation is a pydantic field type, answering 422

A value that is neither empty nor starting with `$` is rejected on write. This is basic
field shape, so it follows the `003`/`004`/`005` precedent of FastAPI's own **422** rather
than a new domain error code.

It lives in a new `backend/app/models/secret_ref.py`, mirroring `models/ids.py` — the
established home for an annotated wire-boundary type — and **not** in `app/secrets.py`,
whose docstring already says that rejecting a non-`$` value *on write* is a different
mechanism belonging to this feature. `resolve_secret` is not edited and keeps handling
read-time resolution alone.

The empty string is **valid input** and means "no pointer" on create and "clear the stored
pointer" on update — see D9. That is why the rule is "empty, or starts with `$`", not
"starts with `$`".

### D9 — The API-key round-trip rule, which is the single easiest thing here to get wrong

The pointer is **never returned by the server**; the table shows only a boolean. On edit,
three states must survive into the request payload and stay distinguishable:

| Payload | Means |
|---|---|
| the field is **omitted** | leave the stored value unchanged |
| the field is present and an **empty string** | clear the stored value |
| the field is present with a value | replace the stored value |

A form that sends `""` for an untouched field deletes the credential on every save. This
is why the update route is a `PATCH` whose model distinguishes omitted from present — the
set of fields actually supplied is what drives the `UPDATE`, never a `None` default. It
carries an explicit `[test]` item in **both** step `005` (the route) and step `007` (the
form).

### D10 — `models` rows persist; they are flags, not a cache of the probe

Enabling upserts a row with `is_enabled = true`; unchecking sets `is_enabled = false`.
**A row is never deleted by an enable or a disable.** That is exactly what makes
`admin-surfaces.md`'s `available ∪ already-enabled` union work: a model that was enabled
but is no longer offered by the server must still render and still be un-checkable, or a
stale enablement can never be cleared. Unique on `(server_id, model_name)`.

The one place rows do disappear is **deleting a connection**, which removes its `models`
rows with it.

### D11 — Failed-probe resilience in the modals

A probe failure surfaces an error and **clears the available list**, but **must not
disturb the existing selection**. Stated as a requirement because the naive implementation
— set `available = []` and derive the checkboxes from it — silently presents "nothing
enabled" and saves that. Mechanically: the enabled set arrives with the **page list
payload**, which never involves the network beyond this instance, and the probe only ever
writes the *available* list. Both modals carry a `[test]` item for it.

### D12 — The use-time validators take a plain pair, and `sessions.model_ref`'s packed form is not fixed here

`no_embedding_model` and `model_not_enabled` ship in step `004` with **no call site** —
sessions arrive in `011`/`017` and embeddings in `024`. Their DoD items are therefore
tested **directly against the service**, not through a session. That is correct and not a
gap.

The chat-model validator takes the **server id and the model name as two plain
arguments** plus the level that set the reference (`character` or `session`, **never
`user`** — UC-050, R1's correction), and raises `model_not_enabled` whose `detail` carries
those three as structured fields, the id as a decimal string.

_TBD: the packed form of `sessions.model_ref` is not fixed by any architecture document —
`data-model.md` calls it an "unvalidated reference" and says nothing about its encoding.
This feature deliberately does **not** fix it: a bare model name is ambiguous across two
registered servers that both offer, say, `gpt-4o`, so some pairing is needed, but choosing
the encoding belongs with the feature that writes the column (`017`). The validator takes
the pair as plain arguments so whichever encoding `017` picks costs one unpack at its own
call site._

### D13 — One timeout setting, covering every outbound call this feature makes

`llm_request_timeout_seconds`, default **30.0**, with the explicit
`RPHELPER_LLM_REQUEST_TIMEOUT_SECONDS` validation alias like every other field. It is
D13's probe timeout, widened to cover the designation's single embedding call because this
feature makes exactly two kinds of outbound call and a second field for one call site
would be noise.

30 s rather than 5 or 10: a models listing is a cheap metadata call for which 30 s is
generous, but a llamaswap server may have to **load** a model before it can answer the
designation's embedding call, and a short budget would fail that spuriously. It is still
short enough that an administrator waiting on a modal is not left indefinitely. Ports are
topology and are not settings; this is not a port.

### D14 — `secret_ref_missing` propagates from the test route as a 500, deliberately

A pointer naming an absent environment variable fails **before** any network call, so the
probe cannot classify it into D6's taxonomy, and inventing a fifth value for it would
break the taxonomy D6 just fixed. The test operation therefore lets `secret_ref_missing`
propagate — **500, with the variable name in `detail`** — and records nothing on the row.
The reason is that it is a configuration fault of *this instance*, not a property of the
connection, and the administrator needs the variable name, which the typed envelope
carries.

UC-011 still holds: the registration is untouched either way. The page renders the error's
message in its inline `Alert`. `outcome.md` notes that the architect may want to revisit
`secret_ref_missing`'s 500 now that it has an admin-facing call site.

### D15 — Nine steps, not the six-to-eight the briefing aimed for

The briefing's suggested cut is followed exactly in shape; three of its bands split
because they do not fit the 200-line budget:

- **the registry service is two steps** (`003` servers and the probe primitive, `004`
  models, designation and the use-time validators) — the two together are roughly 300
  lines of service code, and the designation's measure-the-dimension flow is worth
  verifying on its own;
- **the two `available ∪ already-enabled` modals are two steps** (`008` enabled models,
  `009` embedding) — the briefing authorises keeping them together "only if they fit the
  budget", and two observable pickers plus two modal bodies plus two page wirings is
  comfortably over 200 lines. Step `008` builds the shared picker module both use, so the
  split costs no duplication.

Backend before frontend; every step independently verifiable; every step's Source and Test
file lists disjoint.

### D16 — MobX: no methods and no computed getters

`002`'s D2, confirmed by `003`'s D13 and followed by every store and draft in `003`–`005`,
and **stricter than `ui-conventions.md`'s sketch**, which shows computed getters. A MobX
data class holds **observable fields only**, constructed with
`makeAutoObservable(this, {}, { autoBind: true })`. Every derivation is a **pure free
function taking the data object**; every effect is a free function taking the object plus
an optional `AbortSignal`, which `runInAction`s its writes and **early-returns on
`signal.aborted` before writing**. State and draft modules live under `src/admin/` beside
`main.tsx`, with their derivations and effects in the same module as the class.

One store per page via `useState(() => new XState())`, **never `useMemo`**; stores passed
explicitly as props, no React context; `observer` on every component reading an
observable; **modal open flags and "which row is this targeting" are component-local
`useState`**; a **fresh draft per open** inside a conditionally mounted modal body.

`005`'s `outcome.md` already asks the architect to correct the doc's example; this feature
does not repeat the request.

### D17 — The route surface

Prefix **`/api/admin/llm-servers`**, mirroring `005`'s `/api/admin/users`.

| Method | Path | Does | Answers |
|---|---|---|---|
| `GET` | `/api/admin/llm-servers` | the whole list, no query parameters | 200, the list model |
| `POST` | `/api/admin/llm-servers` | register a connection | **201**, the server model |
| `PATCH` | `/api/admin/llm-servers/{server_id}` | partial update, D9's three states | 200, the server model |
| `DELETE` | `/api/admin/llm-servers/{server_id}` | remove the registration and its `models` rows | **204** |
| `POST` | `/api/admin/llm-servers/{server_id}/test` | UC-011's own capability | 200, the typed test result |
| `GET` | `/api/admin/llm-servers/{server_id}/available-models` | the probe's listing | 200, the names |
| `POST` | `/api/admin/llm-servers/{server_id}/models` | **replace** the enabled set | 200, the enabled names |
| `POST` | `/api/admin/llm-servers/{server_id}/embedding-model` | designate, measuring the dimension | 200, the server model |
| `DELETE` | `/api/admin/llm-servers/{server_id}/embedding-model` | clear the designation | **204** |

Notes that are decisions, not incidentals:

- **`PATCH` for the update, against `005`'s named-action-route preference.** `005` chose
  named actions because "disable", "reset password" and "change role" are three rules with
  three transactions that would otherwise hang off optional fields of one model. A server
  registration is the opposite case: one entity, one rule, and D9's contract is *literally*
  "which fields were supplied", which is what `PATCH` means.
- **The enabled set is replaced by `POST`, not `PUT`.** `frontend/src/shared/api.ts`'s
  `HttpMethod` union is `GET | POST | PATCH | DELETE` — there is no `PUT` helper, and
  adding one to a shared module for one call site is out of this feature's scope. `POST`
  with the full set is replace semantics either way.
- **There is no `GET .../models` route.** The enabled names ride on the list payload, so
  the modals get them without a second round-trip and — the load-bearing part — **without
  the network**, which is what makes D11's resilience natural rather than careful.
- **Clear-designation is server-scoped** rather than a page-level literal path, so it
  cannot collide with `{server_id}` in the route table. `admin-surfaces.md` puts
  "Clear Embedding (conditional)" in the row menu, which is exactly this shape.
- **No route is keyed on anything but a server id**, and no route returns a session, a
  user, or a count of either — the mechanical form of R5.

### D18 — Clearing the embedding designation is confirmed; enabling and disabling models are not

`ui-conventions.md` lists three confirmed actions and explicitly invites FEAT-004's planner
to revisit the set. Two changes:

- **Delete a connection** stays confirmed, as the doc has it, through the shared
  `ConfirmModal`.
- **Clear Embedding is added.** It is irreversible in effect: with no designation every
  semantic path fails as `no_embedding_model` rather than substituting a model (R4), and
  re-designating requires a fresh measuring call. The consequence sentence says that and
  **names no count**.

Saving the enabled-model set is **not** confirmed — it is a form submit in its own modal,
fully reversible, and R5 forbids the only sentence that would make a confirm informative.

## Vocabulary

| Term | Means here |
|---|---|
| **connection** / **registration** | a row in `llm_servers`; deleted outright, never archived and never disabled (`ui-conventions.md`'s per-entity choice) |
| **kind** | `llamaswap` or `openai`; a presentation label, **never a dispatch key** (D5) |
| **pointer** | the literal `"$NAME"` in `api_key_ref`; never a credential |
| **the probe** | the one primitive in `services/llm_registry.py` that talks to a server, exposed as two routes |
| **outcome** | one of D6's four typed values |
| **enabled model** | a `models` row with `is_enabled = true`; the authority behind R4 |
| **the designation** | the at-most-one `models` row with `is_embedding_designated = true`, carrying `embedding_dim` |
| **use time** | the moment a generation or an embedding is attempted — `011`/`017`/`019`/`024`, not here |

## Step map

| Step | Subject | Depends on |
|------|---------|------------|
| 001 | `llm_servers` + `models`, four error subclasses, the timeout setting, the write-time `"$ENV_VAR"` field type | — |
| 002 | `services/llm/client.py` — construction, the probe call, `embed`; `httpx` promoted to runtime | — |
| 003 | `services/llm_registry.py` — registrations, the probe primitive, test-connection, available models | 001, 002 |
| 004 | `services/llm_registry.py` — the enabled set, designation with its measured dimension, the two use-time validators | 001, 002, 003 |
| 005 | `models/admin_llm.py`, `routers/admin_llm.py` behind router-level `require_role(Role.admin)`, registration | 001, 003, 004 |
| 006 | the page — store, table, row menu, delete confirm, test connection | 005 |
| 007 | the server form modal — create and edit, D9's three states | 006 |
| 008 | the shared picker and the enabled-models modal | 006 |
| 009 | the embedding modal and Clear Embedding | 006, 008 |

## Test conventions inherited

**Backend** (`001`/`003`/`004`/`005`): tests live flat in `backend/tests/` as
`test_<module>.py`, with functions named **`test_<behaviour>__DoD<n>`**, each docstring
citing the DoD clause and its step file. `conftest.py` provides the autouse
`isolated_settings_environment` (clears every `RPHELPER_*` variable and the settings
cache), `db_settings` (a real `.sqlite` **file** under `tmp_path`, never `:memory:`) and
`db_engine`. **There is no shared app or client fixture** — each test module builds its own
`TestClient` from `create_app()` and overrides `get_settings` through
`app.dependency_overrides`, never by mutating a global. This feature adds **one** setting
(D13) and **no** new fixture convention. `services/llm_registry.py` is covered by two test
modules, `test_llm_registry_servers.py` and `test_llm_registry_models.py`, because two
steps write it; that is the one departure from one-file-per-module and it is deliberate.

**Frontend** (`002`/`003`/`004`/`005`): Vitest configured inside
`frontend/vite.config.ts`'s `test` block — a separate `vitest.config.*` is forbidden.
`environment: "jsdom"`, **`globals: false`**, so `describe`/`it`/`expect` are explicit
imports from `"vitest"`. Tests live under `frontend/tests/` mirroring `src/`, named
`*.test.ts` / `*.test.tsx`, each `it` title ending `— DoD-N`.
`@testing-library/react`, `/jest-dom` and `/user-event` are available; `fetch` is stubbed
per test with no network-mocking library. A component test rendering Mantine wraps in
`shared/AppProviders` (or an equivalent `MantineProvider` wrapper). Tests assert
**rendered behaviour**, never internal structure. `npm test` is `vitest run`.
