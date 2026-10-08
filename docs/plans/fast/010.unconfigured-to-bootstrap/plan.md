# fast/010.unconfigured-to-bootstrap — plan

## Goal

When the instance is unconfigured, opening `/`, `/login` or `/admin` lands on the
bootstrap offer. That holds even when the browser still carries a session cookie
from a previous database (US-148). Two changes deliver it:
- the `login` entry probes `/api/health` on mount and hands an unconfigured
  instance on to `/bootstrap/`;
- `require_user` answers 401 instead of 500 for a cookie on a database that holds no
  account (no `users` table, or no users).

Decisions D1 to D4 are in `context.md`. D4 was amended after the verify run's SPEC
fault.

## Source files

```
frontend/src/login/loginGate.ts      # new — the probe's phase store + the free async probe function + the login-local health reader
frontend/src/login/LoginPage.tsx     # run the probe on mount, render per phase, hand off to /bootstrap/ via the existing handOff
backend/app/dependencies.py          # the no-account guard (_refuse_unconfigured) ahead of session resolution, shared by require_user and require_role
backend/app/services/bootstrap.py    # ADDED (D4 amendment) — one new transaction-neutral read: "does any user exist"; is_configured untouched
```

`frontend/src/login/main.tsx`, `loginDraft.ts`, every `bootstrap/` (frontend) file
and every `shared/` file are **not** in scope.

## Test files

```
frontend/tests/login/LoginPage.test.tsx                # update existing cases to answer /api/health; add the probe cases
backend/tests/test_unconfigured_session.py             # new — the guard on schema-less and zero-user databases, users-without-admin, and the configured controls
frontend/tests/entries.test.tsx                        # CONDITIONAL — only its fetch stub for the login entry, and only if it now fails because of the mount probe
```

`frontend/tests/login/loginDraft.test.ts`, `frontend/tests/bootstrap/*`,
`backend/tests/test_auth_router.py`, `backend/tests/test_health.py` and the bootstrap
service tests are not in scope. Do not edit them; they must keep passing (DoD-13).

## Interface intent

**`frontend/src/login/loginGate.ts` (new).** It has no import side effects. Its name
does not collide in letter case with any sibling (`frontend-structure.md`'s
case-collision rule).

- **Health reader type.** This is a login-local type for the part of the
  `/api/health` body this entry reads: `configured`, a boolean. It is not imported
  from `bootstrap/` (that would be a cross-entry import) and not added to `shared/`
  (D2).
- **Gate store class.** This is a MobX data class holding the gate's phase. The
  phase is one of three values:
  - *probing*: the initial phase, in which no form is shown;
  - *form*: the sign-in form is shown;
  - *leaving*: a navigation to bootstrap has been issued, and no form is shown.

  The class has no methods beyond what the MobX convention needs. Derivations and
  actions are free functions.
- **Probe function (free, async).** It takes the gate, an `AbortSignal` and a
  navigation callback (a function taking a URL). It issues exactly one
  `GET /api/health` through the shared client and then does one of three things:
  - If `configured` is strictly `false`, it sets the phase to *leaving* and calls the
    navigation callback once with `/bootstrap/`.
  - If `configured` is strictly `true`, it sets the phase to *form*.
  - For any other body, or any thrown failure (an `ApiError` of any code), it sets
    the phase to *form* (D1). It neither notifies nor retries.

  If the signal is aborted, whether before the request settles or because the
  request rejected with the abort, it writes nothing and navigates nothing. It
  never rejects; every outcome is absorbed.

**`frontend/src/login/LoginPage.tsx` (changed).**
- `LoginPageProps` is unchanged. It has `draft` and the optional `handOff`, whose
  default is `documentNavigation.assign`. The same `handOff` serves both
  navigations: `/` after sign-in, as today, and `/bootstrap/` from the gate.
- On mount, the page creates one gate (held for the page's lifetime) and starts the
  probe with an `AbortController`. On unmount it aborts. This sits alongside the
  existing submit-abort cleanup and does not replace it.
- Rendering:
  - The root `<div data-entry="login">` always renders.
  - Inside it, the form and everything in it (fields, submit, general alert) render
    **only** in the *form* phase.
  - In *probing* and *leaving*, the root is empty: no spinner and no text.
- Sign-in behaviour inside the form is unchanged.

**`backend/app/services/bootstrap.py` (changed, D4 amendment).**
- **"Any user exists" read (new, public).** It takes a connection and returns a
  boolean: true exactly when a `users` table exists **and** holds at least one row,
  whatever the rows' roles or enabled state.
  - On a schema-less database it returns false and raises nothing. It reuses the
    module's existing `sqlite_master` check for `users`.
  - The row check is an existence check, not a count.
  - It is transaction-neutral: it opens no transaction of its own and leaves none
    open on the connection, matching `is_configured`'s posture.
- `is_configured` and every other function in the module are unchanged.

**`backend/app/dependencies.py` (changed).**
- **The no-account guard (`_refuse_unconfigured`, frozen signature unchanged).** It
  takes the connection and returns nothing. When the new "any user exists" read
  reports false, it raises `NotAuthenticatedError`. Otherwise it returns and the
  normal session resolution proceeds.
  - It does **not** consult `is_configured`. A database with users but no
    administrator passes the guard.
  - It issues no SQL of its own; the query lives in the service.
- `require_user` calls the guard on the cookie-present path, before
  `resolve_session`. `require_role(min_role)` inherits it through its dependency on
  `require_user`.
- No exported signature changes.
- The no-cookie path is unchanged: it raises 401 and issues no SQL.

## Definition of done

The following terms are used throughout:
- **"Unconfigured instance"**: a fresh, schema-less database, the `health_client`
  pattern in `context.md`.
- **"Zero-user database"**: the declared schema applied with no rows in `users`.
- **"Users-without-admin database"**: the declared schema with at least one
  roleplayer account and no administrator. This is the shape `test_auth_router.py`'s
  seeded fixtures have.
- **"Configured instance"**: a database with at least one administrator account.
- **"Shows the form"**: the username and password fields and the submit control are
  present.
- **"Shows no form"**: none of those is present.

Frontend, in `frontend/tests/login/LoginPage.test.tsx`:

1. `[test]` **Unconfigured → bootstrap.** The page is mounted with `/api/health`
   answering 200 `{ configured: false, … }`. Then:
   - the navigation (the injected `handOff`, or `documentNavigation.assign` when none
     is injected) is called **exactly once**, with `/bootstrap/`;
   - the page shows no form, both before and after the probe settles.

   (US-148.AC-2; UC-001/UC-002 alt 1a)
2. `[test]` **Configured → form.** With `/api/health` answering 200
   `{ configured: true, … }`, the page shows the form after the probe settles and
   never navigates. (US-148.AC-4, the no-offer part only)
3. `[test]` **Nothing in flight.** While `/api/health` is unresolved, the page shows
   no form and the `data-entry="login"` root is present. (US-148.AC-2, "not a sign-in
   form")
4. `[test]` **Failure falls through to the form, once.** Each of the following leads
   to the form with **no navigation**:
   - fetch rejects (transport failure);
   - a 503 with a non-JSON body;
   - a 500 with a well-formed error envelope;
   - a 200 whose body lacks `configured`;
   - a 200 whose `configured` is a non-boolean.

   After the form appears, with fake timers advanced at least 5000 ms, there has
   been **exactly one** request to `/api/health`. No not-ready text is shown, and the
   mocked `notifyFailure` is not called. (D1; the login entry has no not-ready state)
5. `[test]` **Abort on unmount.** If the page is unmounted while `/api/health` is
   still pending and the request then settles (with `configured: false`, or by
   rejecting with an abort), there is no navigation, no thrown or unhandled
   rejection, and no `notifyFailure` call.
6. `[test]` **The probe is the only mount request.** On mount the page issues
   exactly one request, a `GET` to `/api/health`. It makes no request to `/api/me`
   and no `POST` until the user submits.
7. `[test]` **Sign-in is unchanged on a configured instance.** The file's existing
   sign-in cases still assert what they asserted before:
   - success hands off to `/`;
   - a refusal renders in the general alert;
   - every other existing case.

   Their only change is that the stub answers `/api/health` with
   `{ configured: true }`. (US-148.AC-4)

Backend, in `backend/tests/test_unconfigured_session.py`:

8. `[test]` **Stale cookie on an unconfigured instance → 401, not 500.**
   `GET /api/me` with a session cookie (any token value, set the way
   `test_auth_router.py`'s `_with_cookie` does) answers **401** with the error
   envelope code `not_authenticated`. (US-148.AC-3)
9. `[test]` **The same through `require_role`.** On an unconfigured instance, a
   cookie-bearing `GET /api/admin/users` answers 401 `not_authenticated`, not 500.
   (US-148.AC-3, the administration address)
10. `[test]` **No cookie on an unconfigured instance** still answers 401
    `not_authenticated` on `GET /api/me`.
11. `[test]` **The guard writes nothing.** After the requests in DoD-8 and DoD-9, the
    database still has no `users` table, and `GET /api/health` still reports
    `configured: false`. (US-148.AC-3: the bootstrap offer is still reachable)
12. `[test]` **Configured controls.** On a configured instance:
    - a valid session cookie gets `GET /api/me` → 200 with that user;
    - an unknown cookie token gets 401 `not_authenticated`;
    - a valid admin cookie gets `GET /api/admin/users` → 200.

    (US-148.AC-4: authentication is unchanged once configured)

Gates and live:

13. `[manual/live]` From `backend/`: `<py> -m pytest` is fully green, which includes
    the untouched `test_auth_router.py`, `test_health.py` and the bootstrap tests.
    This explicitly covers the existing tests whose fixtures seed users without an
    administrator, the ones that failed under the first D4. `<py> -m mypy app` and
    `<py> -m ruff check .` are clean. From `frontend/`: `npm test` is fully green,
    `npm run typecheck` is clean, and `npm run build` emits the same four entry
    documents.
14. `[manual/live]` **End-to-end on an empty database.** Start the dev servers with an
    emptied data file and no cookie, then open `/`, `/admin`, `/login` and `/login/`.
    Each ends on the bootstrap offer, with no lasting sign-in form and no not-ready
    screen. (US-148.AC-1, US-148.AC-2)
15. `[manual/live]` **End-to-end with a stale cookie.** Sign in on a configured
    instance, stop the backend, empty the data file and restart, then open `/`,
    `/admin` and `/login` in the same browser. Each ends on the bootstrap offer
    within one or two page loads. There is no endless not-ready screen.
    (US-148.AC-3)
16. `[manual/live]` **Configured instance.** On a configured instance, opening `/`,
    `/admin` and `/login` never shows the bootstrap offer. (US-148.AC-4, the no-offer
    part only)

Backend additions after the D4 amendment, in
`backend/tests/test_unconfigured_session.py`:

17. `[test]` **Zero-user database + cookie → 401.** On a zero-user database:
    - `GET /api/me` with a session cookie answers **401** `not_authenticated` (not
      500, not 200);
    - a cookie-bearing `GET /api/admin/users` answers the same 401.

    (US-148.AC-3)
18. `[test]` **Users without an administrator are not refused by the guard.** On a
    users-without-admin database, a valid session cookie for a roleplayer account
    gets `GET /api/me` → **200** with that user's identity. The guard does not
    refuse a database that has users merely because it has no administrator.
    (D4 amendment; no AC)
19. `[test]` **The "any user exists" service read.** Called directly with a
    connection, it returns:
    - false on a schema-less database, raising nothing;
    - false on a zero-user database;
    - true on a users-without-admin database;
    - true on a configured instance.

    Afterwards the connection can still open a new transaction (`begin()` succeeds),
    so the read left none open. (D4 amendment)

## Out of scope

- A database lost while someone is mid-use (US-148's note).
- Main-app deep links other than `/`. They reach `/login` the same way today, but
  nothing asserts it.
- Any change to the `bootstrap` entry's behaviour, files or types. That includes
  moving `HealthConfiguredResponse` (D2).
- Any change to `is_configured`, `require_unconfigured` or `/api/health`.
- Changing the shared client's 401 target, or adding a branch to the `app` or
  `admin` boot sequences.
- A not-ready screen, a retry loop or a failure notification on the `login` entry.
- Guarding `resolve_session` or any other service, or other cookie-bearing routes
  (logout included) beyond what `require_user` / `require_role` cover.
- Clearing the stale cookie on the 401.
- Any behaviour of a users-without-admin database beyond DoD-18. In particular, the
  login entry's redirect to bootstrap on `configured: false` there is accepted, not
  fixed.
- The "behave as before (UC-003)" clause of US-148.AC-4, whose rewording is pending
  with the user.
