# Fast feature 010 — unconfigured-to-bootstrap

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-10-07 |

## Files Changed

- `frontend/src/login/loginGate.ts` — `probeLoginGate` body: one `GET /api/health`, strict `configured === false` → "leaving" + navigate `/bootstrap/`, else "form"; aborted → no write/no navigate; never rejects
- `frontend/src/login/LoginPage.tsx` — one `LoginGate` per page lifetime, probe on mount with its own `AbortController` aborted on unmount, form rendered only in phase "form", `handOff` passed as `navigate`
- `backend/app/dependencies.py` — `_refuse_unconfigured` body via `any_user_exists` (D4 amendment); `require_user` calls it on the cookie-present path before `resolve_session` (`require_role` inherits it)
- `backend/app/services/bootstrap.py` — `any_user_exists` body: `sqlite_master` check for `users`, then a `LIMIT 1` existence read; transaction-neutral like `is_configured`

## Skeleton

### Frozen interface (2026-10-07)
- `frontend/src/login/loginGate.ts` — `export type LoginGatePhase = "probing" | "form" | "leaving"` — new
- `frontend/src/login/loginGate.ts` — `export type LoginHealthResponse = { configured: boolean }` — new (login-local, D2)
- `frontend/src/login/loginGate.ts` — `export class LoginGate { phase: LoginGatePhase = "probing"; constructor() { makeAutoObservable(this, {}, { autoBind: true }) } }` — new (data class, complete as declared)
- `frontend/src/login/loginGate.ts` — `export async function probeLoginGate(gate: LoginGate, signal: AbortSignal, navigate: (url: string) => void): Promise<void>` — new (stub throws)
- `frontend/src/login/LoginPage.tsx` — `LoginPageProps` and `LoginPage` unchanged; file not touched by the skeleton. The coder wires the gate (one `LoginGate` per page lifetime, probe started on mount with its own `AbortController`, aborted on unmount, form rendered only in phase "form", `handOff` passed as `navigate`).
- `backend/app/dependencies.py` — `def _refuse_unconfigured(connection: Connection) -> None` — new private helper (stub raises `NotImplementedError`; not yet called). The coder calls it from `require_user` on the cookie-present path before `resolve_session`; `require_role` inherits it through its `Depends(require_user)`. `require_user` / `require_role` signatures unchanged.
- Caller-compile edits (out of Source-files scope): None.

### Re-freeze (2026-10-07) — D4 amendment
- `backend/app/services/bootstrap.py` — `def any_user_exists(connection: Connection) -> bool` — new (stub raises `NotImplementedError`; not yet called). The coder implements it and switches `_refuse_unconfigured`'s predicate from `is_configured` to it.
- `backend/app/dependencies.py` — `def _refuse_unconfigured(connection: Connection) -> None` — unchanged (signature still frozen; not touched by this re-freeze).
- All other frozen signatures above are unchanged. Caller-compile edits (out of Source-files scope): None.

## Tests

### Tests (2026-10-07)
- `frontend/tests/login/LoginPage.test.tsx` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-6, DoD-7 — new "fast/010 —" blocks: configured:false hands off once to `/bootstrap/` (injected and default navigation) with no form before/after; configured:true shows the form and never navigates; pending probe leaves an empty `data-entry="login"` root; transport/503 non-JSON/500 envelope/missing/non-boolean `configured` fall through to the form with exactly one `/api/health` after 6000 ms fake time, no not-ready text, no `notifyFailure`; unmount mid-probe then resolve(false)/abort-reject gives no navigation, no unhandled rejection, no notification; mount issues exactly one GET `/api/health`, no `/api/me`, no POST before submit. DoD-7: every pre-existing case kept its assertions; `stubFetch` now routes `/api/health` to a `{configured:true}` answer through a separate mock (the returned mock still records only non-health requests) and `renderPage` awaits the probe (callers now `await`). The old 004 DoD-12 "no request on mount" cases were retitled to "no request beyond the health probe".
- `backend/tests/test_unconfigured_session.py` — covers DoD-8, DoD-9, DoD-10, DoD-11, DoD-12 — schema-less app: cookie on `/api/me` and `/api/admin/users` → 401 `not_authenticated` (not 500), no cookie → 401, no `users` table created and `/api/health` still `configured:false`; seeded app: valid cookie → 200 with that user, unknown token → 401, admin cookie on `/api/admin/users` → 200. Clients use `raise_server_exceptions=False` so the pre-fix 500 surfaces as a status mismatch.
- `frontend/tests/entries.test.tsx` — not edited (conditional; its login clauses are marker-only and the root renders during the probe). If the red/verify run shows the login entry's unstubbed `/api/health` fetch breaking it, re-route to add a login fetch stub only.
- Re-route (2026-10-07, TEST fault on DoD-5): `LoginPage.test.tsx`'s "fast/010 — abort on unmount" cases now assert, before the unmount, that exactly one GET `/api/health` was issued and is still pending (no form, no navigation). The test's own deferred probe promise carries a no-op catch, so its rejection can no longer surface as an unhandled rejection the page did not cause.
- D4 amendment (2026-10-07): `backend/tests/test_unconfigured_session.py` — covers DoD-17, DoD-18, DoD-19 — zero-user database (schema applied, empty `users`): cookie on `/api/me` and `/api/admin/users` → 401 `not_authenticated`; users-without-admin database: valid roleplayer cookie on `/api/me` → 200 with that identity; `any_user_exists` called directly → false on schema-less and zero-user, true on users-without-admin and on a configured instance, and the connection can `begin()` afterwards. DoD-8..DoD-12 rechecked against the amended terms and left unchanged: DoD-8..DoD-11 use the schema-less database, and DoD-12's fixture seeds an administrator plus a roleplayer, so it matches "configured instance" (at least one administrator).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13..DoD-16 [manual/live, no test], DoD-17 ✓, DoD-18 ✓, DoD-19 ✓

## Notes & Issues

_populated by the coder when worth saying_
