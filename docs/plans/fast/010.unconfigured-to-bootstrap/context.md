# fast/010.unconfigured-to-bootstrap — context

**Realizes:** US-148.AC-1, US-148.AC-2, US-148.AC-3, US-148.AC-4 (FEAT-001;
exercises UC-001 and UC-002, alternate flow 1a). Requirements are in
`docs/product/stories/FEAT-001.first-run-bootstrap.md` and
`docs/product/use-cases/FEAT-001.first-run-bootstrap.md`; they are cited here, not restated.

US-148.AC-4 is testable **only** as "no bootstrap offer is shown". A rewording that
drops "and they behave as before (UC-003)" is pending with the user, so no DoD
item tests that clause.

## The problem as observed

The user emptied the database (no tables, no users) and opened the instance. They
landed on the sign-in form, which can never succeed, instead of the bootstrap offer.
There are two causes:

1. **Nothing routes an unauthenticated visitor to bootstrap.** `/` (the `app`
   entry) and `/admin` (the `admin` entry) each issue `GET /api/me` on boot. Their
   401 makes the shared client (`shared/api.ts`, `decodeErrorResponse`) navigate to
   `/login`. The `login` entry makes no request on mount, so it shows the form.
2. **A stale cookie gives a 500, not a 401.** When the browser still holds a
   session cookie from the previous database, `require_user` calls
   `resolve_session`. That function selects from `auth_sessions` joined to `users`
   with no table guard. On a schema-less database this raises `OperationalError`,
   which is unhandled, so the request answers 500. The client classifies a 500 with a
   malformed body as not-ready (`shared/notReady.ts`). The `app` and `admin` boots
   then re-probe every 2000 ms forever. This is the "endless waiting state" in
   US-148.AC-3. With no cookie, no SQL runs and the 401 path already works.

## Design decision (orchestrator, recorded here)

**One owner of the redirect: the `login` entry.** `/` and `/admin` already reach
`/login` through the shared client's 401 navigation. Teaching the `login` entry
to send an unconfigured instance on to `/bootstrap/` therefore covers all three
addresses. Neither the `app` nor the `admin` boot gains a branch. The chain is:

```
/        ─► GET /api/me ─► 401 ─► shared client ─► /login ─┐
/admin   ─► GET /api/me ─► 401 ─► shared client ─► /login ─┤
/login                                                     ├─► GET /api/health
                                                           │     configured === false ─► /bootstrap/
                                                           │     configured === true  ─► sign-in form
                                                           │     anything else        ─► sign-in form
```

**Frontend, the `login` entry:**
- It issues one `GET /api/health` on mount and reads `configured` alone. It never
  reads `status` or `schema`, because a pre-bootstrap instance answers
  `status: "degraded"`. This is the same rule the `bootstrap` entry follows.
- `configured === false` (strictly): a document navigation to `/bootstrap/` (the
  canonical URL with its trailing slash). The navigation goes through the page's
  existing injectable `handOff`, whose default is `documentNavigation.assign`. No
  new prop is added.
- `configured === true`: the sign-in form renders as it does today.
- **Planner decision D1: anything else is treated as a probe failure.** That covers
  a body that is missing, non-object, or has a non-boolean or absent `configured`.
  Leaving the form needs a positive "unconfigured" answer. A garbled health body
  must not send a user on a configured instance to a page whose create the server
  would refuse anyway. This is stricter than the bootstrap entry's
  `configured === true` reading, and the asymmetry is deliberate. The bootstrap
  entry's safe default is "offer", the login entry's is "form".
- **In flight:** no form fields are rendered. The entry root
  (`data-entry="login"`) still renders, empty, so no flash of the form appears and the
  entry marker other tests may look for stays. This mirrors the app/admin "nothing
  rendered while in flight" rule.
- **Any probe failure** (not-ready, a well-formed error envelope, a transport
  failure, or a malformed body per D1): the form renders. There is **no retry and no
  not-ready screen**, and the failure is not notified. A real outage then
  surfaces on the user's own sign-in attempt, in the form's general alert, exactly
  as today. The server stays the boundary.
- **After navigating to bootstrap:** the form stays unrendered while the document
  navigation completes, so the form does not flash in before the page unloads.
- **Unmount during the probe:** the request is aborted. Nothing is written to
  state, nothing navigates, and nothing is reported.

**Planner decision D2: health-response typing stays login-local.** The bootstrap
entry's `HealthConfiguredResponse` (`bootstrap/bootstrapState.ts`) is not moved to
`shared/`. Moving it would edit the bootstrap entry for a one-field type. An import
from `bootstrap/` into `login/` would be a cross-entry import, and
`frontend-structure.md` allows only `shared/` to be imported across entries. The
login entry declares its own reader of `{ configured }`. The duplication is one
field. If a third entry ever needs the probe, it moves to `shared/` (flip condition,
carried in outcome.md).

**Planner decision D3: state follows the MobX convention.** The probe's phase lives
in a small login-local store class with a free async function acting on it
(`frontend-structure.md`, "State — MobX 6, per-page stores, no context"). It does
not live in a custom hook, which the house rule forbids from holding reactive
state, and it is not added to `LoginDraft`. `LoginDraft` is the form draft, and the
probe is not form state.

**Backend: the no-account guard in front of session resolution.** When a session
cookie is present and the database **has no `users` table, or its `users` table
has no rows**, the dependency raises `NotAuthenticatedError` (401,
`not_authenticated`) before it calls `resolve_session`. **A database that has
users but no administrator is not refused by this guard.** Its sessions resolve
exactly as before.

**Planner decision D4 (amended after the verify run's SPEC fault): predicate and
placement.**
- **Predicate: "the database holds at least one user", not `is_configured`.**
  - The first version keyed the guard on `is_configured` (an administrator exists).
    That broke 315 existing backend tests whose fixtures seed schema and users but no
    administrator. It would also have signed everyone out the moment the last
    administrator was demoted.
  - The user decided the guard refuses only when no account can exist: no `users`
    table, or zero rows.
  - "No account exists" is an authentication fact; "no administrator exists" is a
    bootstrap fact. Only the former belongs in `require_user`.
  - Consequently, **session refusal is a strict subset of "bootstrap is open"**, not
    equal to it. On a users-without-admin database, `/api/health` says
    `configured: false` and `require_unconfigured` admits bootstrap, yet a valid
    cookie still authenticates. That combination is accepted. It cannot arise
    through the product (bootstrap always creates an administrator). If it ever
    does, the cost is only that the login entry sends a signed-out visitor to the
    bootstrap offer, which is what US-148 asks for on an unconfigured instance.
- **Predicate home: a new transaction-neutral read in
  `backend/app/services/bootstrap.py`** ("does any user exist"), beside
  `is_configured`. It reuses that module's existing `sqlite_master` check for
  `users`, so it is safe on a schema-less database. Then it checks whether at least
  one `users` row exists.
  - It is **not** a query helper inside `dependencies.py`. `dependencies.py` sits on
    the router side of `routers → services → db`, and that split puts every SQL
    statement in `services/` (`backend-structure.md`, "Routers versus services").
    `services/health.py` exists for exactly this reason, and `require_unconfigured`
    likewise delegates to the service rather than querying.
  - **This adds one Source file** (`services/bootstrap.py`). That is strictly
    necessary to keep SQL out of `dependencies.py`. The skeleton adds one stub; the
    frozen `_refuse_unconfigured(connection: Connection) -> None` signature is
    unchanged.
- **Guard home: `_refuse_unconfigured` in `app/dependencies.py`**, unchanged from the
  first version:
  - It is called from `require_user` on the cookie-present path before
    `resolve_session`. `require_role` inherits it through its `Depends(require_user)`.
  - Guarding inside `resolve_session` stays rejected: it would add an `auth →
    bootstrap` service-to-service import and widen what a `None` session means for
    every caller.
  - Importing `services/bootstrap.py` from `dependencies.py` follows the existing
    direction, because `dependencies.py` already imports `services/auth.py`.

## Facts and constraints for the coder

- **Frontend files today** (`frontend/src/login/`):
  - `index.html`.
  - `main.tsx`: a module-local `LoginRoute` creates the `LoginDraft` and renders
    `LoginPage`.
  - `LoginPage.tsx`: `LoginPageProps` has `draft` and an optional `handOff`, whose
    default is `documentNavigation.assign`. It calls `handOff("/")` on sign-in. Its
    only `useEffect` is an abort cleanup. Its root is `<div data-entry="login">`.
  - `loginDraft.ts`: `LoginDraft`, `submitLogin`, `LoginOutcome`.

  `main.tsx` needs no change. The page owns its probe.
- **Shared client** (`frontend/src/shared/api.ts`):
  - `apiGet<T>(path, signal?)` throws an `ApiError` on every failure, including
    transport failure, a malformed body, and a well-formed envelope.
  - `documentNavigation.assign(url)` is the document-navigation seam.
  - Any 401 already navigates to `/login`. That target does not change.
- **Canonical URLs** are `/bootstrap/` and `/login/`. nginx and the Vite dev plugin
  (fast/009) 302 the slash-less forms. Navigate to `/bootstrap/` directly to skip
  the hop.
- **The backend guard runs only when a cookie is present.** With no cookie,
  `require_user` already raises 401 without SQL, and that stays so.
- **`is_configured` is not called by the guard**, and its own behaviour and callers
  are unchanged.
- **The new service read must leave the connection usable.** It must leave no
  transaction open, so a handler's later `with conn.begin():` still works. Follow
  the posture `is_configured` already has on request connections (it runs in front
  of the bootstrap create, which then opens its own transaction).
- **Accepted cost:** every request with a cookie now runs two small reads before
  resolving the session: the table check, and a one-row existence check (not a
  count). Flip condition: if per-request auth cost ever shows, narrow the guard to
  run only after `resolve_session` fails on a missing table.
- **`NotAuthenticatedError`** is in `backend/app/errors.py` (code
  `not_authenticated`, 401). It needs no new error code.

## Test-side facts

- Frontend tests use vitest, jsdom and @testing-library/react. Fetch is stubbed
  with `vi.stubGlobal("fetch", vi.fn(...))`. Navigation is stubbed with
  `vi.spyOn(documentNavigation, "assign").mockImplementation(() => {})`, or through
  the injectable `handOff`.
- **`frontend/tests/login/LoginPage.test.tsx`**: the existing cases must answer
  `GET /api/health` with `{ configured: true }`. The `## Tests` record shows this is
  already done.
- `frontend/tests/entries.test.tsx` may be touched only for a login fetch stub, and
  only if needed.
- Backend: `backend/tests/test_auth_router.py` covers `/api/me` against seeded
  fixtures. Those fixtures seed users **without** an administrator, which is why
  the `is_configured` predicate failed. Its helpers `_me`, `_with_cookie` and
  `_assert_envelope(response, status, code)` show how the cookie is set and how
  envelopes are checked.
  - The **schema-less** pattern is `health_client` in `backend/tests/test_health.py`
    (around lines 77-90): `create_app()`,
    `dependency_overrides[get_settings] = lambda: db_settings`, and a fresh
    schema-less database from conftest's `db_settings` / `db_engine`.
  - A **"users table exists, zero rows"** database is that same fresh database
    after applying the declared schema with no seed rows. The test-coder picks the
    mechanism, for example the schema registry's `metadata.create_all` on the
    conftest engine.
- The new backend file reuses those fixtures. It does not edit `test_auth_router.py`
  or `test_health.py`.

## Commands

Commands come from the root `CLAUDE.md` only. Run the backend from `backend/`
(`<py> -m pytest`, `<py> -m mypy app`, `<py> -m ruff check .`) and the frontend
from `frontend/` (`npm test`, `npm run typecheck`, `npm run build`).
