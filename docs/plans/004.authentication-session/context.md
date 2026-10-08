# Feature 004 — Authentication and session · feature-wide context

## What this feature is

Gives a created account a way in and a way out: a correct credential pair opens a
server-side session and sets an HttpOnly `SameSite=Lax` cookie, every authenticated
request resolves through that session row, a wrong pair and a disabled account are
refused identically, and an ended or expired session returns the person to the login
screen. The agreed boundary is `brief.md` in this folder — its Definition and its Scope
In/Out lists bound every step here. Read it first. Two deliberate departures from it are
recorded below and nowhere else: the **session-refresh route is dropped** (D4) and
**bootstrap's create route is widened to sign the operator in** (D11).

## Product ids

`FEAT-002`, via **UC-004**, **UC-005**, **US-004**, **US-005**, **US-006**, **US-007** —
and **US-001.AC-2**, which belongs to FEAT-001 but was deferred here by
`003/context.md` D9 and `003/outcome.md` C1 (D11 below).

| Criterion | Where it lands |
|---|---|
| US-001.AC-2 | step `004` (the create route mints a session; the hand-off becomes `/`) |
| US-004.AC-1 | steps `001` (the session is opened), `003` (the route), `005` (the form) |
| US-004.AC-2 | step `005` (the hand-off to `/`, for both roles — D12) |
| US-005.AC-1 | steps `001` (the refusal), `003` (its status) |
| US-005.AC-2 | step `005` (the person stays on the login screen, message rendered) |
| US-006.AC-1 | step `001` (a disabled account produces the **same** refusal — D1) |
| US-006.AC-2 | step `005` (the same rendering; there is no disabled-account screen) |
| US-007.AC-1 | step `003` (logout ends the session and clears the cookie) — **the affordance that lets a roleplayer take the action is `008`'s**, per `brief.md`'s Out list, so this criterion is **not fully delivered here** |
| US-007.AC-2 | steps `002`/`003` (an expired or revoked session answers 401), with the browser half inherited from `002/004` DoD-10 |

A `[test]` Definition-of-done item cites the `US-###.AC-#` it verifies wherever one
applies. Items that are structural or architectural obligations rather than product
criteria stand on their own, as they do in `001`–`003`.

## Assumption every step rests on — `002` and `003` are planned, not built; `001` is built

`backend/` **exists**: feature `001.backend-foundation` is built, committed and verified,
so anything it delivers may be bound to exactly. `frontend/` **does not exist at all** —
`002.frontend-foundation` is planned with every step `pending` — and
`003.first-run-bootstrap` is planned with every step `pending`, so its `users` table,
`app/roles.py`, `services/passwords.py`, `already_configured`, `services/bootstrap.py`,
`routers/bootstrap.py` and the whole `bootstrap` entry **do not exist in code**. The
build order is `001 → 002 → fast/001 → 003 → 004`.

Therefore:

- **No step here quotes an exact signature for anything `002` or `003` delivers.** Their
  `## Skeleton` records do not exist, so there is nothing frozen to bind to. Borrowed
  interfaces are named by **role and module path** in prose — "the hashing seam's
  verification operation in `app/services/passwords.py`", "the `Role` enum in
  `app/roles.py`", "the request function in `frontend/src/shared/api.ts`", "the `ApiError`
  type guard in `frontend/src/shared/apiError.ts`" — and the **skeleton agent resolves the
  exact names against the delivered code**.
- The citation for every borrowed interface is the step file that delivers it:
  `docs/plans/002.frontend-foundation/00{4,5,6}.*.md` and
  `docs/plans/003.first-run-bootstrap/00{1,2,3,4,5}.*.md`. Where a step needs a narrow
  fact from one of those, its `<SSS>.context.md` names the file and section rather than
  restating it.
- If the delivered `002`/`003` code contradicts what a step file assumes about it, that
  is a **skeleton hand-back**, not something a coder improvises around.

**What `001` delivers and may be bound to exactly**, because it is built:
`app/config.py`'s `Settings` (explicit `RPHELPER_<FIELD>` aliases per field, `@lru_cache
def get_settings()`), including **`session_cookie_name` and `session_ttl_hours`, which
already exist and have no consumer — `004` is their first**; `app/db/engine.py`'s
`get_connection` dependency, which yields a Core `Connection` and **opens no
transaction**; `app/db/schema.py`'s single `MetaData` and its one-literal-per-table rule;
`app/errors.py`'s `DomainError` base with `code`/`http_status` as class attributes each
subclass sets, one handler registered for the base class through the decorator form;
`app/ids.py`'s snowflake generator, whose single instance lives on
**`app.state.id_generator`**; `app/models/ids.py`'s two annotated aliases, re-exported
from `app/models/__init__.py`; `app/main.py`'s `create_app()` with its frozen ordering and
a **lifespan that runs no DDL**; `app/routers/health.py`, whose docstring already names
`require_user` / `require_role` as this feature's.

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

- `docs/architecture/backend-structure.md` — Layout (`routers/auth.py`,
  `services/auth.py`), "Authorization as router dependencies" (the three dependencies, the
  `require_role` factory and `ROLE_LADDER`), the error model and its wire shape,
  `GET /api/me`, Configuration, the JSON id boundary, routers versus services, Persistence
  access (Core, explicit `begin()`).
- `docs/architecture/data-model.md` — `auth_sessions` (the column list is authoritative:
  `id`, `user_id`, `token_hash`, `created_at`, `expires_at`, `revoked_at`), `users`,
  Identifiers.
- `docs/architecture/domain-rules.md` — "Roles — the ladder every rule below assumes".
- `docs/architecture/frontend-structure.md` — per-entry responsibilities, why `login` is
  its own entry, navigation between entries, the `admin` entry's boot sequence as the
  precedent this feature's dependencies serve, State/MobX, ids-are-strings, The API client.
- `docs/architecture/deployment.md` — **no TLS anywhere** and the `Secure`-flag `_TBD:`,
  the not-ready-yet window, the redaction rule.
- `docs/architecture/ui-conventions.md` — the MobX-draft CRUD convention.
- `docs/architecture/overview.md` — the actor → surface map.
- `docs/product/use-cases/FEAT-002.*.md`, `docs/product/stories/FEAT-002.*.md`, and
  `docs/product/stories/FEAT-001.*.md` for US-001.AC-2.

Cited, never copied. Where a step needs a declaration the architecture gives verbatim
(the `auth_sessions` column list, the wire shape of a domain error, the two snowflake
aliases), the step context points at the section and the skeleton agent reproduces it.

## Files this feature touches

```
backend/
  app/
    db/schema.py            # + the auth_sessions Table literal                (001)
    errors.py               # + invalid_credentials                            (001)
                            # + not_authenticated, insufficient_role           (002)
    services/auth.py        # NEW — authenticate + the session lifecycle       (001)
    roles.py                # + ROLE_LADDER and the pure comparison helper     (002)
    dependencies.py         # NEW — CurrentUser, require_user, require_role,
                            #       and the two cookie writers                 (002)
    models/auth.py          # NEW — the login request and the identity model   (003)
    routers/auth.py         # NEW — login, logout, GET /api/me                 (003)
    main.py                 # + include the auth router                        (003)
    services/bootstrap.py   # creation also opens a session, same transaction  (004)
    routers/bootstrap.py    # + set the session cookie on the 201              (004)
frontend/
  src/
    bootstrap/CreateAdminForm.tsx   # hand-off target becomes `/`              (004)
    login/main.tsx                  # placeholder route table replaced         (005)
    login/LoginPage.tsx             # NEW — the sign-in screen                 (005)
    login/loginDraft.ts             # NEW — the draft, validators and submit    (005)
```

**`frontend/src/login/index.html` is not touched.** `002/006` already creates it as a
document with lang, charset, viewport, a title, one mount element and a module script
pointing at the sibling `main.tsx`; nothing here changes any of that, so it appears in no
step's Source files. **`backend/app/models/bootstrap.py` is not touched either** — the
token travels in a cookie and never in a response body, so the create response's shape is
unchanged (D11).

**Out of scope, and a step that creates one is out of scope:** a session-refresh or
session-extension route (D4); any sliding expiry; a password-reset or change-password
path; a rehash-on-verify path; rate limiting, lockout, attempt counting or a CAPTCHA
(nothing in `docs/product/` asks for one); a "remember me" control; a session-listing or
revoke-other-sessions surface; the admin gate's frontend behaviour and any account
management (`005`); the user menu's logout affordance (`008`); an `account_disabled`
error or any disabled-account screen (D1); a not-ready-yet screen in the `login` entry
(D14); any `/api/me` call from the `login` or `bootstrap` entries; `db/drift.py`,
`db/sync.py`, Alembic, any `versions/` directory, any DDL at startup; a new setting of any
kind — `session_cookie_name` and `session_ttl_hours` already exist and are the only two
this feature reads.

## Cross-cutting constraints every step holds

**Routers versus services stays strict.** The router owns path, method, models,
dependencies, status code and the cookie set/clear, and nothing else; it issues **no SQL**
and holds no rule. The service takes plain arguments, returns plain results or raises a
typed error, and **never imports `fastapi`, never sees a `Request`, never knows a status
code** — which is exactly why the session service returns a **token and an expiry** and
the *router* is what turns them into a cookie. Direction is one-way:
`routers → services → db`.

**Transaction boundaries are the service's own `with conn.begin():` blocks.** `001`'s
connection dependency opens none.

**The JSON id boundary.** `GET /api/me`'s `id` crosses the wire as a **decimal string**
through `001`'s outbound annotated alias; a bare `int` id field on a model is the defect.
`auth_sessions.id` and `auth_sessions.user_id` are snowflakes minted from the generator on
**`app.state`** — never a module global, never `AUTOINCREMENT`. On the frontend an id is a
`string` end to end, and the `login` entry reads no id at all.

**The redaction rule** (`deployment.md`) binds every log line at every level: ids as
decimal strings, error codes, counts, statuses — **never a password, never a hash, never a
session token, and never a username on a failed login**. A log line that would let someone
reading the file tell a wrong-password attempt from an unknown-username attempt undoes D1
in the log file.

**No DDL at startup.** `main.py`'s lifespan still runs nothing. `auth_sessions` is added
to `db/schema.py`'s single `MetaData` as a `Table(...)` literal and is created by `003`'s
bootstrap `create_all` (`003/context.md` D8), which stays correct with no edit there
because the registry is the single source of truth. Stated plainly: **an instance
bootstrapped *before* `004` ships would have no `auth_sessions` table.** That is out of
scope — the build order is `003 → 004`, and `007` owns drift remediation for any instance
that ends up behind.

**Frontend is TypeScript only.** No `.js`, `.jsx`, `.mjs` or `.cjs` is authored anywhere
under `frontend/`, and there is no linter — `tsc --noEmit` is the only static gate.

**The store convention** (`002`'s D2, `003`'s D13, `ui-conventions.md`): a **data class
with observable fields only — no methods and no computed getters**,
`makeAutoObservable(this, {}, { autoBind: true })` in the constructor, with pure
derivations and effectful free functions (taking the data object plus an optional
`AbortSignal`, `runInAction`-ing their writes and early-returning on an aborted signal)
**in the same module**; state and draft modules live **under the entry folder beside
`main.tsx`**; one store per page via `useState(() => new XState())`, never `useMemo`;
stores passed explicitly as props, no React context; `observer` on anything reading an
observable.

**The `login` entry is the only surface reachable unauthenticated on a configured
instance** (`frontend-structure.md`). It must not acquire an authenticated store or any
API surface beyond its own routes: it issues **no `GET /api/me`**, probes nothing on
mount, and calls exactly one route, and only when the form is submitted. `002/006` gives
it an `index.html`, a `main.tsx` with **no `basename`** and a placeholder route table
carrying a `login` marker; this feature replaces the route table wholesale and touches the
document not at all.

**Failures render in place**, so **`notifyFailure` is called nowhere in this feature**
(`003`'s D12 reasoning applies again: a login form's failure has a place to render).
`002/006` DoD-12's scan — Mantine's notification API is imported by
`shared/notifyFailure.ts` alone — stays true, unchanged and untouched.

## Decisions — settled, with their reasoning

### D1 — The refusal is uniform, always; `account_disabled` is raised nowhere

**User decision, and `brief.md`'s Definition is the binding text.** A wrong username, a
wrong password and a **correct password on a disabled account** produce the **same** typed
refusal: the same code, the same HTTP status and the same message. The login screen
renders one message for all three and never says which happened. The reconciliation that
would have distinguished the disabled case once the password was right was offered and
**rejected**.

Two consequences carried by this plan rather than left implicit:

- `backend-structure.md`'s error table lists `account_disabled` — *"Raised when: Login by
  a disabled account (FEAT-002)"*. After this feature **nothing raises it**.
  `outcome.md` asks the architect to strike it, noting that FEAT-003's planner may
  reintroduce it if account management turns out to need it.
- `frontend-structure.md` lists `account_disabled` among the codes the API client's call
  sites branch on and gives the `login` entry a **"disabled-account message"** screen in
  its per-entry responsibilities table. `outcome.md` asks for both to go. **No
  disabled-account screen is built.**

**The distinction must not return through timing.** A refusal that returns measurably
faster when no user row matched tells an attacker which usernames exist, which is exactly
what D1 refuses to tell them through the message. So the authentication path **verifies a
password even when no row matched**, against a fixed decoy hash, before raising. This is
carried as a structural `[manual/live]` item in step `001` — a verifier reads the module —
and deliberately **not** as a timing measurement, because a wall-clock assertion on a
shared CI machine is a flaky test that would be deleted within a month.

### D2 — The refusal is HTTP **400**, not 401 — and this is a trap, not a preference

`002/004` DoD-10 makes the shared API client perform a **document navigation to `/login`
on any 401** and then still throw. If the login route answered 401 for bad credentials,
submitting a wrong password would **reload the login page and destroy the very message
US-005.AC-2 requires the user to see**. The failure would look like "the form does
nothing", and it would be blamed on the form.

So the refusal is **400 Bad Request**: the submitted credential pair is not a valid one,
no identity has been established, and the status never touches the client's 401 branch.
Rejected alternatives, recorded so they are not revisited:

- **401 plus a per-call opt-out in the API client.** It would widen `002`'s contract — one
  shared module gaining a flag for one call site — and every future caller would have to
  know the flag exists.
- **403.** Wrong by definition: nothing has been authenticated, so there is no identity to
  refuse an action to.
- **422.** That is FastAPI's own validation shape, which is not the error envelope; it is
  already spoken for as the empty-field backstop.

Step `005` carries the criterion that makes the trap visible if it is ever re-sprung:
submitting bad credentials leaves the person on the login screen with the message rendered
(US-005.AC-2, US-006.AC-2).

### D3 — `require_user` raises a typed 401, and `require_role` a typed 403

`require_user` refuses with a new domain error, `not_authenticated`, whose `http_status`
is **401** — the status `backend-structure.md` already fixes for `GET /api/me` with no
live session. Here 401 is not a trap but the intended behaviour: an authenticated call
failing on an expired session **should** take the person back to the login screen, which
is US-007.AC-2 and is precisely what the client's 401 rule does.

`require_role` refuses an authenticated caller below the rung with a second new error,
`insufficient_role`, at **403**, which the client deliberately does **not** redirect on
(`002/004` DoD-11) — it is a genuine authorization failure and is rendered.

Both are typed domain errors rather than a bare `HTTPException`, so every non-2xx this
backend produces keeps the one wire shape `001` registered one handler for. `outcome.md`
asks the architect to add all three new codes to the error table.

### D4 — Absolute 720-hour expiry, no sliding, and **the session-refresh route is dropped**

`expires_at` is written **once**, at login, from `Settings.session_ttl_hours` (default
720), and is never moved. Reason: SQLite has a **single writer**, and a compose exchange
holds a request open for the length of a generation
(`backend-structure.md`'s `journal_mode = WAL` rationale). Extending a session on every
authenticated request would turn **every read into a write**, putting the busiest path in
the product behind the one lock the whole database shares.

`brief.md`'s Scope In names "the login, logout and **session-refresh** routes". **The
refresh route is dropped**, and this is recorded here as a deliberate **narrowing of the
brief** so it reads as decided rather than forgotten: with an absolute expiry there is
nothing for a refresh route to do, and a route that re-mints a session on demand is a
sliding expiry with extra steps. `outcome.md` records the lifetime and its **flip
condition** — what would have to become true for sliding to be worth the writes.

The cookie's own lifetime is a hint; **`expires_at` in the row is the authority** (D6).

### D5 — The token is opaque and random, stored as a SHA-256 digest — deliberately **not** Argon2

`auth_sessions.token_hash` holds a **SHA-256 digest** of a high-entropy random token
(`secrets.token_urlsafe`, 32 bytes of entropy). The plaintext token exists **only in the
cookie**; lookup is by digest.

Argon2 is not used here, and the reason is worth recording because the codebase already
depends on it for passwords (`003`'s D1): **Argon2 exists to make low-entropy human
passwords expensive to guess.** A 256-bit random token has nothing to guess, and running a
memory-hard KDF on **every authenticated request** would buy nothing and cost a
deliberately expensive computation per request. The digest is what makes a stolen database
file useless for replaying live sessions, and that is the whole of the requirement.

The token is **never logged** — the redaction rule binds every line.

### D6 — Cookie flags

| Flag | Value | Why |
|---|---|---|
| name | `Settings.session_cookie_name` | the setting exists and this is its first consumer; never a literal |
| `HttpOnly` | on | `frontend-structure.md`: there is no token JavaScript can read, which is why the admin gate is a server round-trip |
| `SameSite` | `Lax` | `brief.md` and `frontend-structure.md` both fix it; cross-entry navigation is same-origin so `Lax` costs nothing |
| `Path` | `/` | it must reach all four entries — `/`, `/login`, `/admin/`, `/bootstrap/` |
| `Secure` | **off** | `deployment.md` records HTTP only, no `listen 443`, no certificate anywhere. A `Secure` cookie would simply never be sent |
| `Max-Age` | the TTL, in seconds | see below |

**`Secure` off is recorded with its flip condition**: the moment TLS termination exists
anywhere in front of this application, `Secure` becomes mandatory —
`deployment.md`'s TLS `_TBD:` already names this cookie's flag as part of that work.

**`Max-Age` matching the TTL rather than a browser-session cookie.** A browser-session
cookie is discarded when the browser closes, which would silently turn a 30-day session
into a "until I close the window" session — a behaviour no product id asks for and one the
operator would experience as random logouts. Matching the TTL also means the browser stops
sending a cookie the server would only reject, so the common expiry case costs no request.
It is a hint and nothing more: the server re-checks `expires_at` on every request, so a
tampered or replayed cookie past its expiry resolves to nothing regardless.

### D7 — What `require_user` resolves — the closure of `brief.md`'s second open question

`brief.md` asks whether `require_role` reads the role from the session row or re-reads
`users`. **It is not open.** `data-model.md`'s `auth_sessions` section states that *every
authenticated request resolves through this table* — which is *why* `GET /api/me` answers
401 for a disabled account — and the table **carries no `role` column** at all. So the
resolution is fixed by the doc, and this plan records it rather than choosing it:

```
cookie ──► digest ──► an auth_sessions row that is NOT revoked and NOT expired
                          └──► join users ──► the account must be is_enabled
                                   └──► CurrentUser: id, username, role (read live)
```

The consequence that matters operationally: **a role change or a disable takes effect on
the caller's next request**, with no session rewrite and no cache to invalidate — which is
what makes FEAT-003's "disabling an account ends that user's sessions" implementable as a
flag flip plus a revoke in one transaction.

### D8 — Where the ladder and the dependencies live

`003/outcome.md` entry 5 suggests the ladder lands "naturally beside" the enum in
`app/roles.py`, and `003/context.md` D6 explicitly leaves `004` free to choose the home.
There is a constraint that suggestion does not account for: **`db/schema.py` imports
`app/roles.py`** for the `role` column's value domain, so putting a FastAPI dependency
factory in `roles.py` would drag `fastapi` into `db/` transitively — an import edge from
the persistence layer to the web framework, created by a convenience.

So the split is:

- **`app/roles.py` keeps `ROLE_LADDER` and a pure "at least this rung" comparison
  helper.** Both are pure data and pure logic, both are still importable by `db/`, and the
  ladder is the thing `domain-rules.md` states.
- **`app/dependencies.py` is new** and holds `CurrentUser`, `require_user`,
  `require_role(min_role)` **and the two cookie writers** (set and clear). It imports
  `fastapi`; nothing in `db/` or `services/` imports it.

It is a **top-level leaf beside `config.py`, `ids.py`, `errors.py` and `roles.py`**, not a
module inside `routers/`, because its consumers are *many* routers — `auth.py` today,
every `admin_*.py` and every roleplayer router later — and putting it in one router would
make every other router import from a sibling router. `003` set no precedent here: its
`require_unconfigured` is declared inside `routers/bootstrap.py` precisely because that
router is its only consumer (`003/context.md` D6), and that reasoning does not transfer.

**The cookie writers live there too**, with the dependencies that read the cookie, because
all four share one fact — the cookie's name and flags — and are consumed by the same two
routers (`auth.py` and, from step `004`, `bootstrap.py`). Two routers each spelling out
`HttpOnly`/`SameSite`/`Path`/`Max-Age` is how a flag drifts between them.

Names considered and rejected: `app/security.py` (implies the crypto, which lives in
`services/`), `app/auth_deps.py` (abbreviation; the Layout uses whole words), and a
`routers/deps.py` (would file a non-router in the router package). `outcome.md` records the
placement **and its divergence from `003/outcome.md` entry 5**, so the architect applies
the corrected placement rather than the suggested one.

### D9 — Logout is idempotent, and never answers 401

`POST /api/auth/logout` answers the **same success** whether or not a live session
resolved: it clears the cookie either way, and sets `revoked_at` when there is a row to
revoke. It carries **no `require_user` dependency**.

Two reasons, both concrete: a 401 there would trip the same document-navigation trap as
D2, in the one place where the person is already on their way out; and signing out of a
session that expired thirty seconds ago is not an error — it is the normal case, and an
error response would leave a stale cookie on the client that only the user could clear.

The response is **204 No Content**: there is nothing to report, and the observable outcome
is the cleared cookie and the revoked row.

### D10 — Route paths

`GET /api/me` is **fixed by `backend-structure.md`** and is owned by `routers/auth.py`.
The login and logout paths are fixed by no doc, so the plan chooses **`POST
/api/auth/login`** and **`POST /api/auth/logout`** — the obvious shape beside `/api/health`
and `/api/bootstrap/create`, and one that leaves room for whatever FEAT-003 needs under the
same prefix. The router therefore carries the `/api` prefix and declares two paths under
`/auth/` plus the doc-fixed `/me` at the prefix root; `/api/me` is deliberately **not**
moved under `/api/auth/` (the doc names it, and three other docs cite it by that path).
`outcome.md` asks the architect to record the surface, exactly as `003/outcome.md` entry 3
did for the bootstrap route.

The login route **answers 200 with the caller's identity** — the same model `GET /api/me`
returns, one model serving both routes. `003`'s gotcha applies again: a route whose
response reports nothing about what just happened is a poorer contract for manual
verification, and `backend-structure.md` wants routes returning pydantic models. **The
`login` entry reads no field of that body** (D12), which step `005` carries as a
criterion. A 204 was considered — it would make the no-role-branch rule mechanical — and
rejected for the two reasons above.

### D11 — `004` delivers US-001.AC-2: bootstrap's create route signs the operator in

**User decision, and a deliberate, user-authorized *widening* of `brief.md`'s Scope In.**
Once the session service exists, `POST /api/bootstrap/create` mints a session and sets the
cookie on its `201`, and the `bootstrap` entry's hand-off becomes a document navigation to
**`/`** instead of `/login`. This closes the deferral `003/context.md` D9 and
`003/outcome.md` C1 recorded, and **completes FEAT-001**.

It gets **its own step** (`004`) so the widening is visible in one place and reviewable,
rather than smeared across the login steps. It touches files `003` owns:
`app/services/bootstrap.py`, `app/routers/bootstrap.py` and
`frontend/src/bootstrap/CreateAdminForm.tsx`. **`app/models/bootstrap.py` is not touched**
— the token travels in a cookie and never in a response body, so the create response's
shape is unchanged.

**The session is opened inside the creation transaction**, not by a second service call
from the router. `003`'s D8 already makes schema-plus-administrator one `with
conn.begin():` so that no half-bootstrapped instance is reachable; extending that block by
one insert keeps the same property for the widened outcome — the operator is created and
signed in, or nothing happened. The router's added work is exactly one thing: putting the
token the service returned into a cookie.

### D12 — Everyone lands on `/` after login; the `login` entry has no role branch

Both roles go to the `app` workspace. An administrator reaches `/admin` from the user menu
(US-093), which is feature `008`'s. The `login` entry therefore contains **no role
branch** and reads no role to decide where to go — it navigates to `/` unconditionally.

This matches the admin gate, which sends a non-admin from `/admin` to `/` and never the
reverse (`frontend-structure.md`'s boot sequence): the app area is the common landing for
both rungs, and the admin area is somewhere you go *from* it. US-004.AC-2 — "the user's
home is shown" — is satisfied by `/` for both actors.

In stage 001 `/` is still `002`'s placeholder `app` document, which is fine and is said
here so nobody reads the empty page as a broken hand-off. The root document's own
deployment seam — `dist/app/index.html` versus nginx's `/` fallback — is recorded in
`002/outcome.md` and is `fast/001`'s to bridge; `004` depends on it but does not fix it.

### D13 — No credential normalization, on either side

The server looks up `username` by **exact match** and compares the password **as
received**. The `login` form sends both fields **exactly as typed** — no trimming, no case
folding, no Unicode normalization. Client-side validation uses a trimmed value only to
decide whether a field is *filled*; it never changes what is sent.

Reason: the stored credential is whatever `003`'s bootstrap form sent, and normalization
applied on one side only makes an account **permanently unreachable** — an operator who
created `" admin"` could never log in as `admin`, and nothing would say why.
`docs/product/` states no normalization rule, so none is invented. Flip condition: if
FEAT-003's account management introduces normalization, it must be applied at creation and
at login **together**, in one change.

### D14 — The `login` entry renders one screen, with failures in place

No not-ready-yet screen, no probe on mount, no sign-out landing screen, no
"already signed in" redirect. `deployment.md`'s not-ready-yet handling belongs to the two
surfaces that make a request **before the user does anything** — the `bootstrap` entry and
the `admin` gate — and this entry makes its only request in response to a submit, where a
transport failure has an obvious place to render: the form's general inline alert
(`003`'s D12, `002`'s D6). `shared/notReady.ts` exists and this entry does not use it.

`frontend-structure.md`'s per-entry table gives `login` a "sign out landing" screen; there
is no such screen, because being signed out *is* landing on the sign-in form and nothing
in `docs/product/` asks for a confirmation page. `outcome.md` asks the architect to record
that.

### D15 — Four assertions from feature `003` become false here, and each is owned by the step that invalidates it

None is an architecture change; all are recorded consequences, here and in `outcome.md`.
The posture is exactly `003`'s D14: **the step that invalidates an assertion owns its
deletion or correction as an explicit DoD item**, every other clause of the affected test
stays intact, and nothing is changed incidentally.

1. **`003/001` DoD-4's purity clause** — that the role enum exposes *no ladder mapping and
   no role-comparison or dependency helper*. Step `002` adds both, so the clause is
   deleted; the rest of that assertion (two members, their values) stays and is joined by
   this feature's own ladder assertions.
2. **`003/003` DoD-2** — that the create response sets **no** `Set-Cookie` header and
   carries no session field. Step `004` deletes the `Set-Cookie` half and replaces it with
   the opposite assertion; **the "no token or session field in the body" half stays true
   and stays asserted** (D11).
3. **`003/002` DoD-13** — that nothing in that step declares `auth_sessions`, mints a
   token, sets a cookie or adds a setting. Step `004` deletes the "mints a token" clause;
   the "declares no table", "sets no cookie" (the service still sets none — the router
   does) and "adds no setting" clauses stay true.
4. **`003/005` DoD-5 and DoD-11** — that the bootstrap hand-off targets `/login`. Step
   `004` **corrects the target to `/`**; the rest of both items — that the hand-off runs,
   and that it runs once — is unchanged.

### D16 — The login entry holds a draft and no page store

`003`'s D13 fixed store placement: state and draft modules live under the entry folder
beside `main.tsx`. This entry gets **`loginDraft.ts` and nothing else**. A `loginState.ts`
would hold no field that is not already the draft's — the page has exactly one state, and
a store holding nothing is a store somebody will later find a use for.

## Vocabulary

| Term | Means here |
|---|---|
| **session** | a row in `auth_sessions` — never the RP-domain `sessions` entity, which this feature does not touch |
| **token** | the opaque random value the cookie carries; exists in plaintext only in the cookie (D5) |
| **the refusal** | the one uniform login rejection: wrong username, wrong password or disabled account, indistinguishable (D1) |
| **live session** | an `auth_sessions` row that is not revoked, not past `expires_at`, and whose `users` row is enabled (D7) |
| **the ladder** | `{roleplayer: 0, admin: 1}` (`domain-rules.md`), compared as "at least this rung" |
| **the hand-off** | the document navigation after a successful submit — `/` from both the login form and, from step `004`, the bootstrap form |

## Step map

| Step | Subject | Depends on |
|------|---------|------------|
| 001 | the `auth_sessions` table literal, `invalid_credentials`, and `services/auth.py` — authenticate plus the session lifecycle | — |
| 002 | `ROLE_LADDER` and the comparison helper, `not_authenticated` / `insufficient_role`, and `dependencies.py` — `CurrentUser`, `require_user`, `require_role`, the cookie writers | 001 |
| 003 | `models/auth.py`, `routers/auth.py` (login, logout, `GET /api/me`), router registration | 001, 002 |
| 004 | bootstrap signs the operator in — the service's widened transaction, the cookie on the 201, the hand-off to `/`, and D15's corrections | 001, 002 |
| 005 | the `login` entry — route table, draft, form, submit, hand-off | 003 (the route contract) |

This refines the decomposition the briefing proposed in one place, and the reason is
dependency direction: **the refusal error moves into step `001`, beside the service that
raises it**, because a service and the error it raises must land together or the earlier
step depends on the later one. Step `002` declares the two errors *its own* dependencies
raise, by the same rule. That is also what `003` did — `already_configured` was declared
in the same step as the predicate that raises it.

Steps `001`–`004` are the backend seam and `005` the frontend one. `004` is the single
step that crosses the line, deliberately: it is one decision (D11) whose frontend half is
a one-line change to a hand-off target, and splitting it would make the widening
invisible in both halves.

## Test conventions inherited

**Backend** (`001/context.md`, as built): tests live in `backend/tests/` as
`test_<module>.py`, named `test_<behavior>__DoD<n>`. `conftest.py` holds an **autouse**
`isolated_settings_environment` fixture that clears every `RPHELPER_*` variable and calls
`get_settings.cache_clear()` on both sides of each test; `db_settings` yields settings
pointing at a **real `.sqlite` file under `tmp_path`**, never `:memory:`; `db_engine`
builds the engine from them. **There is no shared app or client fixture** — each test
module builds its own `TestClient` locally and overrides settings through
`app.dependency_overrides[get_settings]`, never by mutating a global. `004` adds no
setting and no fixture convention.

**Frontend** (`002/context.md`): **Vitest** + Testing Library + jsdom, configured in
`vite.config.ts`'s `test` block. Tests live under **`frontend/tests/`, outside `src/`,
mirroring `src/`'s tree**, named `*.test.ts` / `*.test.tsx`. `globals` is **off** —
`describe` / `it` / `expect` are imported explicitly. `frontend/tests/setup.ts` holds **no
fetch stub**: `fetch` is stubbed per test, with no network-mocking library. A component
test rendering Mantine wraps in `shared/AppProviders`. Tests assert **rendered
behaviour**, not internal structure.
