# fast/010.unconfigured-to-bootstrap — outcome

Intended architecture changes for `/architect` to apply at finalization. These
are grouped by target file. Requirements: US-148.AC-1..AC-4, UC-001/UC-002 alt 1a.

## `docs/architecture/frontend-structure.md`

### Section: "The `login` entry"

- **Change:** replace the bullet "No request on mount at all — no `/api/me`, no
  probe, no gate" with the following:
  - The login entry makes **one `GET /api/health` on mount and reads `configured`
    alone**, never `status` or `schema`, which is the bootstrap entry's rule.
  - `configured === false` (strictly) causes a document navigation to `/bootstrap/`
    through the page's injectable `handOff`.
  - `configured === true` shows the form.
  - **Anything else, or any failure, also shows the form**, with no retry and no
    notification. Leaving the form requires a positive "unconfigured" answer
    (fast/010 D1).
  - Nothing of the form renders while the probe is in flight or after the hand-off;
    the `data-entry="login"` root renders empty.
  - The probe's phase is a login-local MobX store (`login/loginGate.ts`) with a
    free probe function.
  - Still no `/api/me` and no role gate.
- **Reason:** US-148.AC-1..AC-3 require an unconfigured instance to lead to the
  bootstrap offer, and the login entry is the one place every unauthenticated visit
  already reaches. The old bullet's rationale ("it makes no request before the user
  acts") no longer holds.

- **Change:** reword the bullet "No not-ready-yet state". The entry **still has no
  not-ready-yet state**, but for a new reason: the probe's only job is to detect a
  positive "unconfigured". Every failure, not-ready included, falls through to the
  form, and the user's own sign-in attempt surfaces any real outage in place.
  `shared/notReady.ts`'s consumer list is unchanged: bootstrap and the admin gate,
  plus the app boot.
- **Reason:** without this, a reader would conclude that "it now makes a request,
  so it needs a not-ready screen" and build one. That would put a second re-probe
  loop in front of a form that works whenever the server does.

### Section: "Navigation between entries" (or a new short subsection beside it)

- **Change:** record the **unconfigured route** as a named chain:
  - `/` (app boot) and `/admin` (admin gate) both get 401 from `/api/me`. The
    shared client then navigates to `/login`, and the login probe sends
    `configured === false` on to `/bootstrap/`.
  - **The login entry is the single owner of the redirect to bootstrap.** Neither
    boot sequence gains a branch, and the shared client's 401 target stays `/login`.
  - A deep link into the app takes the same path, but no requirement pins it.
- **Reason:** this two-hop chain is invisible from any one entry's subsection. It is
  exactly what someone shortens by adding a health probe to the app or admin boot,
  which would create a second owner of the same behaviour.

### Section: "The `bootstrap` entry" / "Not-ready-yet — one shared classification"

- **Change:** note that the `{ configured }` health-body type has **two
  entry-local declarations**:
  - `bootstrap/bootstrapState.ts`'s `HealthConfiguredResponse`;
  - the login entry's reader in `login/loginGate.ts`.

  They read the field with deliberately different safe defaults. Bootstrap treats
  non-`true` as unconfigured, so it offers. Login treats only `false` as
  unconfigured, so it shows the form. **Flip condition:** when a third entry needs
  the probe, lift the type (and, if the defaults can be reconciled, the reader)
  into `shared/`.
- **Reason:** frontend-structure.md permits cross-entry imports only through
  `shared/`. A one-field type did not justify editing the bootstrap entry
  (fast/010 D2).

## `docs/architecture/backend-structure.md`

### Section: "Authorization as router dependencies" — "What `require_user` resolves"

- **Change:** prepend a step to the resolution diagram:

  ```
  cookie present → no users table, OR users table empty
                     → NotAuthenticatedError (401 not_authenticated); no session lookup
  ```

  - The guard is shared by `require_user` and `require_role`; `require_role`
    inherits it through `require_user`.
  - State the rule: **a session cookie never authenticates on a database that holds
    no account.** That means no `users` table, or a `users` table with zero rows.
- **Reason:** on a schema-less database, `resolve_session`'s join raised
  `OperationalError`, which surfaced as a 500. The client classifies that as
  not-ready, which left `/` and `/admin` re-probing forever (US-148.AC-3).

- **Change:** record that the guard's predicate is **deliberately not
  `is_configured`** (fast/010 D4, amended after a SPEC fault).
  - A database that **has users but no administrator** is not refused by this
    guard. `require_user` resolves its sessions as before.
  - The guard therefore refuses on a **strict subset** of the states in which
    `/api/health` reports `configured: false` and `require_unconfigured` admits
    bootstrap. It refuses only the states where no session could be valid, because
    no account exists.
  - The rejected alternative was keying the guard on `is_configured` ("refuse
    exactly when bootstrap is open"). That made the guard depend on the admin
    population, so any admin-less database with real accounts became
    sign-in-proof. The 315 existing backend tests whose fixtures seed users without
    an administrator showed this at once.
  - Name this so nobody "aligns" the two predicates later.
- **Reason:** "no account exists" is a fact about authentication. "No administrator
  exists" is a fact about bootstrap. Only the former belongs in the
  authentication dependency.

- **Change:** record the placement (fast/010 D4):
  - The guard is a private helper in `app/dependencies.py`, called from
    `require_user` on the cookie-present path before `resolve_session`.
  - Its predicate is a **transaction-neutral read in `services/bootstrap.py`**
    ("does the database hold any user"), beside `is_configured` and reusing its
    `sqlite_master` check for `users`. The read lives there so that
    `dependencies.py` issues no SQL itself (the routers-versus-services split, the
    same reason `services/health.py` exists). The import follows the existing
    `routers → services` direction, as `dependencies.py` already imports
    `services/auth.py`.
  - Guarding inside `resolve_session` was rejected: it would add an `auth →
    bootstrap` service-to-service import to the exception table and widen the
    meaning of a `None` session for every caller.
  - `dependencies.py`'s layout comment gains "and the no-account guard".
- **Reason:** someone will otherwise move the check into `services/auth.py` "where
  the SQL is", or inline a query into `dependencies.py`.

- **Change:** record the accepted cost and its flip condition:
  - Every cookie-bearing request now runs the guard's two small reads (the table
    check, then a one-row existence check) before session resolution.
  - **Flip condition:** if per-request auth cost ever shows, narrow the guard to
    run only after `resolve_session` fails on a missing table.
- **Reason:** a decision taken without measurement needs its flip condition.

### Section: `## /api/health`, the `configured` bullet

- **Change:** add the **login entry** as a consumer of `configured`, beside the
  bootstrap entry. It reads `configured` alone, like the bootstrap entry.
- **Reason:** the bullet currently names the bootstrap entry as the only consumer.

### Section: Layout, the `services/` block

- **Change:** `services/bootstrap.py` now also carries the "any user exists" read
  used by the dependencies' no-account guard.
- **Reason:** this records the module's second consumer, `dependencies.py`.

## `docs/architecture/quick-reference.md`

### Section: "The four frontend entries" (around lines 395-415)

- **Change:** add one line after the app-boot paragraph:
  - **The login entry probes `/api/health` once on mount.** `configured === false`
    leads to `/bootstrap/`; anything else leads to the form. It has no not-ready
    state.
  - The unconfigured route for `/` and `/admin` is their 401 → `/login` → that
    probe.
- **Reason:** the dense index currently implies that the login entry makes no
  request, which is now false.

### Section: invariants (wherever `require_user` / authentication invariants are listed)

- **Change:** add "a session cookie never authenticates on a database with no users
  table or no users: 401 `not_authenticated`, never 500. Users without an
  administrator are not refused by this rule."
- **Reason:** this is the US-148.AC-3 invariant, and it is one line to state.

## Observations
