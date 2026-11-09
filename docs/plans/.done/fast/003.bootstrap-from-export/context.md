# fast/003.bootstrap-from-export — context

**Delivers:** FEAT-001, UC-002, US-002 (AC-1 and AC-2). It also re-asserts UC-003
(the refusal once configured) for the new route. The ids are cited here, never
restated. Open `docs/product/` for the behaviour.

`brief.md` is the agreed boundary. Its Scope Out list bounds `plan.md`'s Out of scope.

## Files involved

Backend (edited):

- `backend/app/services/transfer_import.py`: holds `import_database(connection, body)`
  (around line 1110), the whole-database replace from plan 031. It takes no user
  and opens its own `with connection.begin():`. Inside that transaction it runs, in
  order:
  1. `_require_replaceable_database`. It refuses with `DatabaseNotEmptyError` (409
     `database_not_empty`) unless `users` has 0 rows, or exactly 1 row that is an admin.
  2. `validate_envelope(body, {"database"})`.
  3. `_require_memo_scope_targets`.
  4. `ensure_fts_tables`.
  5. `_wipe_registry_rows`.
  6. `_drop_vector_tables`.
  7. `_write_payload`. An `IntegrityError` here becomes
     `ExportInvalidError(REASON_MALFORMED_PAYLOAD)`, 400 `export_invalid`.

  It does **not** create the schema, so the tables must already exist. Its
  docstring already says that fast/003's bootstrap restore will call it.
- `backend/app/services/bootstrap.py` contains:
  - `is_configured(connection)`: true when the users table exists and holds at
    least one admin. It is read-only and rolls back a transaction it autobegan.
  - `create_first_administrator`: one `with connection.begin():` that re-checks
    `is_configured`, then runs `metadata.create_all`, `ensure_fts_tables`, the
    admin insert and `open_session`. It logs `bootstrap outcome=...` with no secrets.
- `backend/app/routers/bootstrap.py`: `router = APIRouter(prefix="/api/bootstrap",
  dependencies=[Depends(require_unconfigured)])`. The guard raises
  `AlreadyConfiguredError` (409 `already_configured`). The router has one route,
  `POST /api/bootstrap/create` (201, sets the session cookie). Module docstring
  lines 6–11 reserve `POST /api/bootstrap/import` and say "exactly one route
  exists". That text must be updated.

Backend (read-only reference, not edited): `backend/app/routers/admin_db.py:157`.
It is the admin `POST /api/admin/database/import`: raw `dict[str, Any]` JSON body,
calls `import_database`, then `clear_session_cookie`, answers 204. There is no
app-level body-size cap; nginx allows 64m.

Frontend (`frontend/src/bootstrap/`):

- `main.tsx` mounts `BootstrapPage`, which is driven by `BootstrapState`. Its
  `phase` is one of `probing | offer | refusal | not-ready | failed`. Free functions
  `probeHealth`, `startProbeLoop` and others drive it.
- In the offer phase the page renders a Mantine `List`. Its single `List.Item`,
  "Create a new database", holds `CreateAdminMount`. That list is the reserved
  place for the second choice.
- `CreateAdminForm.tsx` and `createAdminDraft.ts` are the pattern to mirror:
  - a small MobX state object;
  - free-function submit with an `AbortController`;
  - the hand-off through `documentNavigation.assign` from `shared/api`.
- Reusable shared pieces:
  - `frontend/src/shared/importFile.ts` `readExportFile(file)`. It rejects with
    `ApiError(CLIENT_UNREADABLE_FILE, …, 0)` on an unreadable or non-JSON file.
  - `apiPost` and `failureMessageOf`.
  - `shared/ConfirmModal.tsx` is **not** used here (Decision 4).

Tests:

- `backend/tests/test_bootstrap_router.py` has the fixtures `application`, `client`
  and the helper `_make_configured`.
- `backend/tests/conftest.py` has `db_settings` and `db_engine`, which give an
  unconfigured, empty SQLite file.
- `backend/tests/test_transfer_import_database.py` has `source_engine`,
  `_seed_source` and `_envelope(engine)`, which calls `export_database`. These
  helpers are module-local, not in conftest. A new test file re-creates
  equivalents; it does not import from another test module.
- Frontend tests live in `frontend/tests/bootstrap/`. They use vitest and
  testing-library, stub `fetch` per test, and wrap in `AppProviders` + `MemoryRouter`.

## Architecture references

- `docs/architecture/backend-structure.md`:
  - "The bootstrap route surface — FEAT-001" reserves `POST /api/bootstrap/import`.
  - `require_unconfigured` is router-level, so the new route inherits the refusal.
- `docs/architecture/transfer.md`:
  - "R5 and the two services that take no `user_id`" covers the opacity rule: no
    preview, counts, table list or diff of an import, before or after. It also
    says the single-admin guard lives in the service.
  - The vec0 drop policy.
  - Auth sessions and translations are never restored.
- `docs/architecture/admin-surfaces.md` "The page's full design" gives the admin
  Import flow: picker, confirm, upload, redirect to `/login`. Failures show in an
  inline red `Alert`, never a notification. This feature mirrors it **minus the
  confirm** (Decision 4).
- `docs/architecture/frontend-structure.md` "Per-entry responsibilities" already
  lists import-an-export in the `bootstrap` entry.

## Decisions (settled by the orchestrator — binding)

1. **One operation, all-or-nothing.** Schema creation (`metadata.create_all` +
   `ensure_fts_tables`) and the whole-database import run inside **one**
   transaction. The work is done by a new in-transaction helper extracted from the
   body of `import_database`:
   - Both callers use the helper: `import_database` (public signature and
     behaviour unchanged, still opening its own transaction) and the new bootstrap
     service function.
   - Transactions are never nested: the helper never calls `begin()`.
   - The bootstrap function re-checks `is_configured` inside its transaction and
     raises `AlreadyConfiguredError`, the same way `create_first_administrator`
     does. It logs a single outcome line with no content.
   - SQLite DDL is transactional in this backend (`backend-structure.md`'s
     transactional-DDL setting). A failed restore therefore leaves no tables, the
     instance stays unconfigured, and bootstrap is still offered.
2. **Route.** `POST /api/bootstrap/import` goes on the existing bootstrap router
   and inherits the guard. Its body is raw JSON (`dict[str, Any]`), the same as
   the admin import. It answers **204** and sets **no cookie**: no session exists
   and the import never restores `auth_sessions`. Errors propagate through the
   single `DomainError` handler, and the router has no try/except. The statuses
   are:
   - 400 `export_invalid`
   - 409 `already_configured`
   - 409 `database_not_empty` (see Accepted consequences)
   - 422 for a non-object body
3. **After the restore** the frontend sends the operator to `/login`. They sign in
   with the export's own credentials (US-002.AC-2). Before the upload, the screen
   says in static copy that credentials and API keys do not travel in an export,
   and that the environment (`.env`) must be supplied separately for the restored
   instance to reach any model server. There is no backend field for this.
4. **Frontend shape.** The offer list gets a second `List.Item`, "Restore from an
   export". It holds a file picker and a restore action:
   - the upload goes through `readExportFile` + `apiPost`;
   - a 204 navigates to `/login`;
   - a failure renders an inline red `Alert` with `failureMessageOf`;
   - the control is disabled while the request is in flight.

   There is **no confirm modal**, because the instance is empty and nothing is
   destroyed. The state and free functions go in a new module (`restoreExport.ts`)
   and the UI in a small component (`RestoreExportForm.tsx`), mirroring
   `createAdminDraft.ts` / `CreateAdminForm.tsx`.
5. **An export without an administrator gets no special handling** (see Accepted
   consequences).

## Accepted consequences and edge facts

- **An export with no admin row** restores, but the instance stays unconfigured,
  so bootstrap is offered again. Whole-database exports come only from the admin
  route, so a real one always contains at least one admin. Accepted, not guarded.
- **Unconfigured but not empty.** This means a `users` table exists with
  roleplayer rows and no admin, which only a hand-damaged file could produce. The
  instance is unconfigured, so the guard passes. The service's
  `_require_replaceable_database` then refuses with 409 `database_not_empty`.
  Accepted, not special-cased.
- **Vector tables.** On a fresh file the vec0 tables do not exist yet. The
  extracted helper's `_drop_vector_tables` must tolerate their absence. It already
  must on an admin-import target that never had them, so the coder should confirm
  this and not assume it. After the restore they stay absent until ensure-on-write
  re-creates them. `transfer.md` records that as a legitimate state, not drift.
- **Opacity (R5).** The bootstrap screen shows nothing about the import's
  contents — no counts, no preview, no table list — before or after. The 204 has
  no body.
- **Logging.** The outcome line may carry the outcome token only. It must never
  carry a username, password, password hash, row count or payload fragment.
- **Body size.** There is no application cap, as on the admin route. nginx's
  `client_max_body_size 64m` is the only limit.
- **Login.** After a restore, the existing login route authenticates against the
  restored `users` rows, because password hashes and roles travel in the export.
  No change to auth is needed.
