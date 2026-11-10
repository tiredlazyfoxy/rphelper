# Decisions — fast-010.unconfigured-to-bootstrap
**Stage:** — · **Feature:** fast/010.unconfigured-to-bootstrap

An unconfigured instance leads every unauthenticated visit to the bootstrap
offer, and a stale cookie on an account-less database answers 401 rather than
500. The contracts are `frontend-structure.md` "The `login` entry" and
"Navigation between entries", and `backend-structure.md` "What `require_user`
resolves". Written at finalization (2026-11-09). The plan's decisions map as:
**D1 → `DEC-F010-1`, D2 → `DEC-F010-2`, D3 → `DEC-F010-3`, D4 → `DEC-F010-4`
(predicate, as amended) and `DEC-F010-5` (placement)**; the accepted cost is
`DEC-F010-6`.

### DEC-F010-1 — The login probe leaves the form only on a strict `configured === false` (D1)
- **Status:** accepted
- **Stage:** — · **Feature:** fast/010.unconfigured-to-bootstrap · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** How does the login entry read `/api/health`, and what does it do with anything other than a clean answer?
- **Decision:** One `GET /api/health` on mount, reading `configured` alone (never `status` or `schema`, since a pre-bootstrap instance answers `status: "degraded"`). Strictly `configured === false` → a document navigation to `/bootstrap/` through the page's existing injectable `handOff` (no new prop). `configured === true` → the form. Anything else — a missing, non-object or non-boolean body, a not-ready answer, an error envelope, a transport failure — → the form, with no retry, no not-ready screen and no notification. While the probe is in flight and after the hand-off, the `data-entry="login"` root renders empty. Unmounting during the probe aborts it and nothing is written, navigated or reported.
- **Reason:** Leaving the form needs a positive "unconfigured" answer: a garbled health body must not send a user on a configured instance to a page whose create the server would refuse. A real outage surfaces on the user's own sign-in attempt, in the form's general alert. This is deliberately stricter than the bootstrap entry, whose safe default is "offer"; the login entry's is "form".
- **Rejected:** A not-ready screen with a re-probe loop in front of the form — a second loop in front of a form that works whenever the server does.
- **Lands in:** `frontend/src/login/loginGate.ts`; `frontend/src/login/LoginPage.tsx`
- **Cites:** `frontend-structure.md` § The `login` entry

### DEC-F010-2 — The `{ configured }` reader stays entry-local in two places (D2)
- **Status:** accepted
- **Stage:** — · **Feature:** fast/010.unconfigured-to-bootstrap · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Should the login entry reuse the bootstrap entry's health-response type?
- **Decision:** No. `bootstrap/bootstrapState.ts`'s `HealthConfiguredResponse` stays where it is, and `login/loginGate.ts` declares its own reader of `{ configured }`. The two read the field with deliberately different safe defaults (DEC-F010-1).
- **Reason:** Only `shared/` may be imported across entries; moving the type would edit the bootstrap entry for a one-field type. **Flip condition:** when a third entry needs the probe, lift the type — and the reader, if the defaults can be reconciled — into `shared/`.
- **Rejected:** Importing from `bootstrap/` into `login/` — a cross-entry import.
- **Lands in:** `frontend/src/login/loginGate.ts`
- **Cites:** `frontend-structure.md` § cross-entry imports only through `shared/`

### DEC-F010-3 — The probe's phase lives in a login-local MobX store (D3)
- **Status:** accepted
- **Stage:** — · **Feature:** fast/010.unconfigured-to-bootstrap · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Where does the probe's state live?
- **Decision:** In a small store class in `login/loginGate.ts` with a free async probe function acting on it. Not in a custom hook, and not added to `LoginDraft`.
- **Reason:** The house rule forbids a custom hook from holding reactive state, and `LoginDraft` is the form draft; the probe is not form state.
- **Lands in:** `frontend/src/login/loginGate.ts`
- **Cites:** `frontend-structure.md` § State — MobX 6, per-page stores, no context

### DEC-F010-4 — The no-account guard's predicate is "any user exists", not `is_configured` (D4, amended)
- **Status:** accepted
- **Stage:** — · **Feature:** fast/010.unconfigured-to-bootstrap · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** user (after the verify run's Fault: SPEC)
- **Question:** On which database states does a present session cookie refuse to authenticate?
- **Decision:** Only when no account can exist: no `users` table, or a `users` table with zero rows → 401 `not_authenticated`, before any session lookup. A database that has users but no administrator is not refused; its sessions resolve as before. So session refusal is a **strict subset** of "bootstrap is open", not equal to it: on a users-without-admin database `/api/health` says `configured: false` and `require_unconfigured` admits bootstrap, yet a valid cookie still authenticates. That combination is accepted; it cannot arise through the product (bootstrap always creates an administrator), and if it does the only cost is that the login entry sends a signed-out visitor to the bootstrap offer.
- **Reason:** "No account exists" is a fact about authentication; "no administrator exists" is a fact about bootstrap. Only the former belongs in the authentication dependency. Named so nobody "aligns" the two predicates later.
- **Rejected:** Keying the guard on `is_configured` ("refuse exactly when bootstrap is open") — the first version. It made the guard depend on the admin population: it broke 315 existing backend tests whose fixtures seed users without an administrator, and it would have signed everyone out the moment the last administrator was demoted.
- **Supersedes:** the plan's first version of D4 (the `is_configured` predicate), plan-local, no DEC id.
- **Lands in:** `backend/app/dependencies.py`; `backend/app/services/bootstrap.py`
- **Cites:** `backend-structure.md` § What `require_user` resolves

### DEC-F010-5 — Placement: a guard in `dependencies.py`, its read in `services/bootstrap.py` (D4)
- **Status:** accepted
- **Stage:** — · **Feature:** fast/010.unconfigured-to-bootstrap · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Where do the guard and its database read live?
- **Decision:** The guard is the private `_refuse_unconfigured(connection)` in `app/dependencies.py`, called from `require_user` on the cookie-present path before `resolve_session`; `require_role` inherits it through `Depends(require_user)`. Its predicate is `any_user_exists`, a new transaction-neutral read in `services/bootstrap.py` beside `is_configured`, reusing that module's `sqlite_master` check for `users` (so it is safe on a schema-less database) and then a one-row existence check, not a count. It leaves no transaction open, so a handler's later `with conn.begin():` still works. `dependencies.py`'s layout comment names "the no-account guard". With no cookie, `require_user` still raises 401 without any SQL.
- **Reason:** `dependencies.py` sits on the router side of `routers → services → db`, which puts every SQL statement in `services/` (the reason `services/health.py` exists and `require_unconfigured` delegates). Importing `services/bootstrap.py` from `dependencies.py` follows the existing direction, as `dependencies.py` already imports `services/auth.py`.
- **Rejected:** Guarding inside `resolve_session` — it would add an `auth → bootstrap` service-to-service import and widen what a `None` session means for every caller. A query helper inside `dependencies.py` — SQL on the router side. Moving the check into `services/auth.py` "where the SQL is" — the same `auth → bootstrap` coupling.
- **Lands in:** `backend/app/dependencies.py`; `backend/app/services/bootstrap.py`
- **Cites:** `backend-structure.md` § What `require_user` resolves, § Routers versus services

### DEC-F010-6 — Accepted cost: two small reads per cookie-bearing request
- **Status:** accepted
- **Stage:** — · **Feature:** fast/010.unconfigured-to-bootstrap · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** What does the guard cost, and when would that be wrong?
- **Decision:** Every request carrying a cookie runs the guard's two small reads (the table check, then the one-row existence check) before session resolution. Accepted without measurement.
- **Reason:** A decision taken without measurement needs its flip condition; the reads are a table check and a one-row existence check, not a count. **Flip condition:** if per-request auth cost ever shows, narrow the guard to run only after `resolve_session` fails on a missing table.
- **Lands in:** `backend/app/dependencies.py`
- **Cites:** `backend-structure.md` § What `require_user` resolves
