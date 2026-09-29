# Feature 004 — Authentication and session · intended documentation changes

Planner section: the `docs/architecture/` changes the architect applies at finalization,
grouped by target file. Nothing here is applied by the planner or the coder.

The entries at the end are **recorded consequences, not architecture changes**, and are
listed so they are not lost — they must not be dressed up as design decisions.

---

## `docs/architecture/backend-structure.md`

### 1 — The error table: strike `account_disabled`, add three codes

- **Section:** "The error model", the named-errors table.
- **Change:** **Remove the `account_disabled` row.** After FEAT-002 nothing raises it: a
  wrong username, a wrong password and a **correct password on a disabled account** all
  produce the same refusal with the same code, status and message, and the login screen
  renders one message for all three. Record in one line that FEAT-003's planner **may
  reintroduce it** if account management turns out to need a distinguishable code for an
  administrator-facing surface — the row is struck because it has no caller, not because
  the concept is wrong. Add three rows in its place:

  | `code` | Raised when | `detail` | `http_status` |
  |---|---|---|---|
  | `invalid_credentials` | A login attempt fails for **any** reason — unknown username, wrong password, or a disabled account (FEAT-002) | nothing | **400** |
  | `not_authenticated` | A guarded route is reached with no session cookie, or one that does not resolve to a live session | nothing | **401** |
  | `insufficient_role` | An authenticated, enabled caller's role is below the required rung | nothing — **it names neither the caller's role nor the required one** | **403** |

- **Reason:** the table is the registry an agent looks a code up in, and this feature both
  removes one and adds three. The uniform refusal is a product-visible decision
  (`brief.md`'s Definition) and belongs beside the code that implements it.

### 2 — Why the refusal is 400 and not 401

- **Section:** beside the `invalid_credentials` row, or in the error model's prose.
- **Change:** record the reason in two sentences, because it looks like a mistake to
  anyone who has written a login route before. The SPA's shared API client performs a
  **document navigation to `/login` on any 401** and then still throws
  (`frontend-structure.md`'s API client rules), so a 401 from the login route would
  **reload the login page and destroy the message** US-005.AC-2 requires the user to see.
  400 keeps the refusal off that branch. Record the rejected alternatives: **401 plus a
  per-call opt-out** in the client (it would widen a shared module's contract for one call
  site), and **403** (nothing has been authenticated, so there is no identity to refuse an
  action to).
- **Reason:** a later reader "correcting" the status to 401 would break the login screen in
  a way that presents as "the form does nothing" and would be blamed on the form.

### 3 — The authentication route surface

- **Section:** "Authorization as router dependencies", or beside `GET /api/me`.
- **Change:** record the surface FEAT-002 delivers, owned by `routers/auth.py` under the
  `/api` prefix:

  | Route | Answers | Notes |
  |---|---|---|
  | `POST /api/auth/login` | **200** + the caller's identity (id as a decimal string, username, role), **and `Set-Cookie`** | no authorization dependency; **never answers 401** (entry 2); the body carries no token |
  | `POST /api/auth/logout` | **204**, cookie cleared | **idempotent and carries no `require_user`** — the same answer whether or not a live session resolved; revokes the **calling** session only |
  | `GET /api/me` | as already documented | now real, and its 401-on-disabled is mechanically true through `require_user` (entry 4) |

  Record that the identity model is **one model serving both `GET /api/me` and the login
  route**, and that **there is no session-refresh route** (entry 5).
- **Reason:** the doc fixes `/api/me` and no other auth path, and the paths are now real.
  `003/outcome.md` entry 3 did the same for the bootstrap route.

### 4 — Where `CurrentUser`, `require_user` and `require_role` live — **correcting `003/outcome.md` entry 5**

- **Section:** "Authorization as router dependencies", beside the `require_role` snippet.
- **Change:** record the placement, **and record that it diverges from what FEAT-001's
  outcome suggested**, so the architect applies this one rather than that one:
  - **`app/roles.py` keeps the enum, `ROLE_LADDER` and one pure "at least this rung"
    comparison.** It stays free of `fastapi`.
  - **`app/dependencies.py` is new** — a top-level leaf beside `config.py`, `ids.py`,
    `errors.py` and `roles.py` — holding `CurrentUser`, `require_user`,
    `require_role(min_role)` **and the two session-cookie writers** (set and clear).

  The reason `003/outcome.md` entry 5's "naturally beside it in the same module" does not
  work: **`db/schema.py` imports `app/roles.py`** for the `role` column's value domain, so
  a FastAPI dependency factory in `roles.py` would drag `fastapi` into `db/`
  transitively. Record why it is not inside a router either — its consumers are *many*
  routers, so one router owning it would make every other router import from a sibling
  (unlike `require_unconfigured`, whose only consumer is `routers/bootstrap.py`, which is
  why FEAT-001 put it there). Record that the cookie writers live beside the dependencies
  because all four share one fact — the cookie's name and flags — and are used by two
  routers.

  Record what `require_user` resolves, since three docs depend on it:
  **cookie → digest → an `auth_sessions` row that is not revoked and not expired → join
  `users` → the account must be enabled → a `CurrentUser` carrying id, username and
  `role` read live from `users`.** Consequence: **a role change or a disable takes effect
  on the caller's next request**, with no session rewrite. This answers `brief.md`'s open
  question, and it was never really open: `data-model.md` states that every authenticated
  request resolves through `auth_sessions`, and that table carries no `role` column.
- **Reason:** the doc shows `ROLE_LADDER` and `require_role` in a snippet with no module
  named, FEAT-001's outcome proposed a home that creates an import edge nobody wants, and
  four later features will copy whichever one is written down.

### 5 — Session lifetime: absolute 720 hours, no sliding, no refresh route

- **Section:** beside Configuration's `session_ttl_hours`, or in the auth surface above.
- **Change:** record that `expires_at` is written **once, at login**, from
  `Settings.session_ttl_hours` (default 720) and is **never moved**, and that there is
  consequently **no session-refresh route** — `brief.md` named one and the plan dropped it
  deliberately. Reason to record: SQLite has a **single writer**, and an SSE compose
  exchange holds a request open for the length of a generation; extending a session on
  every authenticated request would turn **every read into a write** and put the busiest
  path in the product behind the one lock the whole database shares.
  **Flip condition:** if sessions ever need to survive activity beyond the absolute window
  — a product requirement for "stay signed in while working", or a TTL short enough that
  people are logged out mid-roleplay — then sliding expiry becomes worth the writes, and
  the cheapest form is a bounded touch (rewrite `expires_at` at most once per N minutes)
  rather than a write per request.
- **Reason:** `brief.md` recorded the lifetime as an open question, the user settled it,
  and a dropped scope item with no recorded reason reads as an omission.

### 6 — The session token: opaque and random, stored as a SHA-256 digest

- **Section:** beside the secret-pointer pattern, or with the auth surface.
- **Change:** record that `auth_sessions.token_hash` holds a **SHA-256 digest** of a
  **32-byte `secrets.token_urlsafe`** token, that the plaintext exists **only in the
  cookie**, and that lookup is by digest. Record explicitly that this is **deliberately
  not Argon2**, with the reason, because the codebase already depends on Argon2 for
  passwords: Argon2 exists to make **low-entropy human passwords** expensive to guess; a
  256-bit random token has nothing to guess, and running a memory-hard KDF on **every
  authenticated request** would cost a deliberately expensive computation for no gain. The
  digest is what makes a stolen database file useless for replaying live sessions, which
  is the whole of the requirement. Record that the token is **never logged**.
- **Reason:** "we hash passwords with Argon2 and session tokens with SHA-256" looks
  inconsistent until the difference between the two inputs is written down, and the
  "fix" — Argon2 on every request — would be a real performance defect.

### 7 — The session cookie's flags

- **Section:** with the auth surface, cross-referenced from `deployment.md` (entry 12).
- **Change:** record the flags and each reason: the name from
  `Settings.session_cookie_name` (never a literal); **`HttpOnly`** (there is no token
  JavaScript can read, which is why the admin gate is a server round-trip);
  **`SameSite=Lax`**; **`Path=/`** (it must reach all four entries); **`Max-Age` matching
  the TTL** — not a browser-session cookie, because a browser-session cookie would
  silently turn a 30-day session into an "until I close the window" session and would be
  experienced as random logouts, and because matching the TTL stops the browser sending a
  cookie the server would only reject. Record that the cookie's lifetime is a **hint** and
  `expires_at` in the row is the **authority**.
  **`Secure` is off**, because `deployment.md` records HTTP only with no TLS anywhere.
  **Flip condition:** TLS termination anywhere in front of this application makes `Secure`
  mandatory.
- **Reason:** the flags are stated in prose across three docs and implemented in one place;
  a cookie flag that drifts between the doc and the writer is invisible until someone is
  silently never authenticated.

---

## `docs/architecture/data-model.md`

### 8 — `auth_sessions`, as built

- **Section:** `auth_sessions`.
- **Change:** record what FEAT-002 declares: all six columns
  (`id`, `user_id`, `token_hash`, `created_at`, `expires_at`, `revoked_at`), with
  `revoked_at` **nullable and NULL until revoked** (the row is never deleted, so a
  revocation stays observable), `user_id` carrying a **declared foreign key to `users.id`**
  and an index (FEAT-003's disable path revokes every row for one user in one
  transaction), and `token_hash` carrying a **unique** index (it is the lookup key on every
  authenticated request). Record that `created_at` / `expires_at` are UTC ISO-8601 text in
  **one fixed format**, because mixed formats make the expiry comparison silently wrong.
  Record that the table is created by **FEAT-001's bootstrap `create_all`**, since the
  registry is the single source of truth and there is no DDL at startup — and that an
  instance bootstrapped **before** FEAT-002 shipped would lack it, which is FEAT-005's
  drift surface, not FEAT-002's problem.
  Cross-reference entry 6 for what `token_hash` actually holds.
- **Reason:** the column list is authoritative but silent on nullability, indexes and who
  creates the table, and FEAT-003 is the next writer of every one of those.

---

## `docs/architecture/frontend-structure.md`

### 9 — Strike `account_disabled` from the API client's branch list

- **Section:** "The API client", the list of codes the UI must branch on specifically.
- **Change:** **remove `account_disabled`.** No backend code raises it (entry 1), so no
  call site can branch on it. Add `invalid_credentials` in its place, with the note that
  the only surface that branches on it is the `login` entry's form and that it renders
  **one fixed message** which never says which of the three causes applied.
- **Reason:** a code in this list is a contract the frontend is told to honour; one that
  the backend never sends is a branch somebody will write and never be able to exercise.

### 10 — The `login` entry's shape, and the two screens it does not have

- **Section:** "Per-entry responsibilities" (the `login` row), as a subsection mirroring
  the `admin` entry's "Boot sequence".
- **Change:** rewrite the `login` row's Screens cell and record the shape:
  - **Remove "disabled-account message".** There is no such screen: a disabled account
    receives the identical refusal and the identical rendering as a wrong password
    (entry 1, `brief.md`'s Definition).
  - **Record that "sign out landing" is the sign-in form itself**, not a second screen.
    Being signed out *is* arriving at the form, and nothing in `docs/product/` asks for a
    confirmation page.
  - Record the entry's boot shape, as the counterpart to the `admin` entry's: **no request
    on mount at all** — no `/api/me`, no probe, no gate — one form, one route
    (`POST /api/auth/login`), every failure rendered **in place** in the form's general
    alert, and a **document navigation to `/` on success for both roles, with no role
    branch** (an administrator reaches `/admin` from the user menu, which is FEAT-020's
    surface). Record that it therefore needs **no not-ready-yet state**: it makes no
    request before the user acts, which is the condition that created that state for the
    `bootstrap` entry and the `admin` gate.
- **Reason:** the doc names three screens for this entry, one of which must not be built
  and one of which is not a screen; and the `admin` entry's boot section is the precedent a
  reader will compare against.

### 11 — Per-entry store placement: a page may hold a draft and no store

- **Section:** "State — MobX 6, per-page stores, no context", extending the precedent
  FEAT-001 sets (`003/outcome.md` entry 11).
- **Change:** one line: a page whose entire state *is* its form holds a **draft module and
  no page-state module** — `src/login/loginDraft.ts` with no `loginState.ts`. Reason to
  record: a store holding no field the draft does not already hold is a store somebody will
  later find a use for, and the convention is "one subject, one module", not "one page,
  two modules".
- **Reason:** FEAT-001 established state-plus-draft as the shape; without this line the
  next planner adds an empty page store for symmetry.

---

## `docs/architecture/deployment.md`

### 12 — The `Secure` flag, beside the TLS `_TBD:`

- **Section:** "TLS — none, deliberately recorded as such".
- **Change:** the `_TBD:` already names "the session cookie's `Secure` flag, which is not
  set today (FEAT-002)". Update it to record that FEAT-002 has now **shipped** the cookie
  with `Secure` **off** and with the flip condition attached (entry 7), so the `_TBD:` is
  now a concrete change surface — one function in `app/dependencies.py` — rather than an
  unexamined gap.
- **Reason:** the `_TBD:` predicted this and should now point at the code that implements
  it, so the TLS work has a checklist rather than a memory.

### 13 — `/login` without a trailing slash must resolve to the login document

- **Section:** beside the per-entry `try_files` fallbacks.
- **Change:** record that **`/login` (no trailing slash) is a load-bearing path, not a
  convenience**: the shared API client navigates to exactly `/login` on any 401
  (`frontend-structure.md`), and FEAT-001's bootstrap refusal links to exactly `/login`.
  The configured block is `location /login/ { ... }`, which does **not** match the
  slash-less path — it falls to the catch-all, which is the same root-fallback seam
  `002/outcome.md` already records as unbridged. State which mechanism closes it (a
  redirect, a second `location = /login`, or whatever the root fix turns out to be) and
  name `fast/001` as the owner.
- **Reason:** two features now navigate to that exact path, and the failure mode is a
  session expiry that lands on the wrong document — which presents as "logging out breaks
  the app" and is diagnosed nowhere near nginx.

---

## `docs/architecture/overview.md`

### 14 — Stack decision list: session mechanics, and the deferrals around them

- **Section:** the stack decision list, plus the deferred section.
- **Change:** one compact entry recording the session mechanism — **server-side sessions
  in `auth_sessions`, an opaque 32-byte random token in an HttpOnly `SameSite=Lax` cookie,
  stored as a SHA-256 digest, with an absolute 720-hour expiry** — cross-referencing
  entries 5, 6 and 7 for the reasoning rather than repeating it. In the deferred section,
  record what FEAT-002 deliberately does **not** build, each with the reason: **no
  session-refresh or sliding expiry** (entry 5); **no rate limiting, lockout or attempt
  counting** (nothing in `docs/product/` asks for one, and a self-hosted single-user
  instance on a trusted LAN is not the threat model `deployment.md` describes — record it
  as a deferral so it is a decision rather than an oversight); **no "remember me"**; **no
  password reset or change-password path** (FEAT-003's); **no rehash-on-verify** (the
  standing consequence of `003/outcome.md` entry 1's flip condition, still unbuilt and
  still owned by no feature); **no session-listing or sign-out-everywhere surface**.
- **Reason:** every one of these is the first thing a reviewer looks for in an
  authentication feature, and a deferral with no recorded reason gets re-proposed at every
  review.

---

## Recorded consequences — not architecture changes

### C1 — US-001.AC-2 is now delivered, and FEAT-001 is complete

`003/outcome.md` C1 recorded the deferral: FEAT-001 shipped **without** signing the
operator in. FEAT-002's step `004` closes it — `POST /api/bootstrap/create` mints a session
inside its existing transaction and sets the cookie on its 201, and the `bootstrap` entry's
hand-off becomes a document navigation to **`/`**.

When this feature is finalized, `docs/product/`'s id registry should flip **US-001 from
partially delivered to delivered**, naming `004.authentication-session` as the plan that
delivered AC-2 — a `/product-spec` action, not an architecture edit.

### C2 — US-007.AC-1 is only half delivered here

`POST /api/auth/logout` ends the session and clears the cookie, and the person's next
authenticated call returns them to the login screen. **The affordance that lets a
roleplayer take the action is `008`'s** — `brief.md`'s Out list assigns the user menu's
logout control to it. So US-007 should stay **partially delivered** in the registry,
naming `008` as the plan that owns the affordance. No DoD item in this feature claims the
user-facing half, and none may be added to make coverage look complete.

### C3 — Four earlier assertions are deleted or corrected, deliberately

Each is owned by the step that invalidates it, as an explicit DoD item, with every other
clause of the affected test left intact — the posture `003/context.md` D14 established.

- **`003/001` DoD-4's purity clause** (the role enum exposes no ladder mapping and no
  comparison helper) is **deleted** by step `002`, which adds both. The two-members clause
  stays.
- **`003/003` DoD-2's `Set-Cookie` clause** (the create response sets no cookie) is
  **deleted** by step `004` and replaced with its opposite. The "no token or session field
  in the body" half stays true and stays asserted.
- **`003/002` DoD-13's "mints a token" clause** is **deleted** by step `004`. Its
  "declares no `auth_sessions`", "sets no cookie" and "adds no setting" clauses stay true.
- **`003/005` DoD-5 and DoD-11's hand-off target** is **corrected** from `/login` to `/`
  by step `004`. That the hand-off runs, and runs once, is unchanged.

All four are consequences of a feature's criteria being true only until the feature that
was always going to extend them lands. None is an architecture change, and none should be
recorded as one.

### C4 — `require_role` ships with no consumer

`brief.md` claims the ladder and the `require_role(min_role)` factory as FEAT-002's Scope
In, and no admin router exists until `005`. So the factory ships tested and unused, exactly
as FEAT-001's password-verification operation did. It is not dead code to prune, and the
first router to use it adds no new mechanism.

---

_Nothing below this line is written by the planner._

## Observations

- Step 001: `auth_sessions` timestamps are written as `datetime.isoformat(timespec="microseconds")` in UTC (`...T..:..:..ffffff+00:00`) so text comparison of `expires_at` is valid; `users.created_at` from `003` uses plain `isoformat()` (microseconds dropped when zero), so the two tables do not share one fixed-width format. Possible impact: record one timestamp text format in `data-model.md`'s conventions.
