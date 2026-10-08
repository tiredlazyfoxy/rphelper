# fast/003.bootstrap-from-export — plan

Read `context.md` first. Its Decisions 1–5 are binding.

## Goal

An unconfigured instance can be restored from a whole-database export as one
all-or-nothing operation: schema creation and the whole-database import run in a
single transaction. The bootstrap screen offers this as a second choice. It tells
the operator that the environment must be supplied separately, uploads the file,
and on success sends them to `/login` to sign in with the export's own credentials.

## Source files

- `backend/app/services/transfer_import.py`: extract the body of `import_database`
  into an in-transaction helper. `import_database` keeps its signature and
  behaviour.
- `backend/app/services/bootstrap.py`: new restore-from-export service function.
- `backend/app/routers/bootstrap.py`: new `POST /api/bootstrap/import` route. Update
  the module docstring.
- `frontend/src/bootstrap/restoreExport.ts` (new): restore state and free functions.
- `frontend/src/bootstrap/RestoreExportForm.tsx` (new): the restore choice's UI.
- `frontend/src/bootstrap/BootstrapPage.tsx`: add the second `List.Item` to the offer
  phase. If the skeleton finds the offer list in another file of
  `frontend/src/bootstrap/`, it edits that file instead and records the path in
  `## Skeleton`.

Read-only reference (not edited): `backend/app/routers/admin_db.py`,
`frontend/src/bootstrap/CreateAdminForm.tsx`, `frontend/src/bootstrap/createAdminDraft.ts`,
`frontend/src/shared/importFile.ts`, `frontend/src/shared/api*`.

## Test files

New:

- `backend/tests/test_bootstrap_import.py` (new): route and service behaviour against a
  real export. It builds the export with `export_database` from a seeded source
  database, using helpers it defines itself.
- `frontend/tests/bootstrap/RestoreExport.test.tsx` (new): the restore choice in
  the offer phase, the environment notice, the upload, the hand-off and the
  failure display.

Update existing (amended 2026-10-07). These are the feature-032 privacy-audit
tests that model `POST /api/bootstrap/import` as an unbuilt surface (row 5, owner
fast/003). Edit them for **row 5 only**. fast/002 edits the same files for its own
row 74, so every edit below is relative to row 5 and never sets an absolute value.

- `backend/tests/privacy_audit_support.py`:
  - add `EnumeratedRoute(5, "POST", "/api/bootstrap/import", "public", None)` in
    row order, after row 4;
  - remove row 5 from `EXCLUDED_ROWS`;
  - in `UNBUILT_SURFACES`, either retire the row-5 entry or add
    `/api/bootstrap/import` to its `allowed_paths`. The choice must stay consistent
    with the `test_privacy_audit_export_import.py` edit below.
- `backend/tests/test_privacy_audit_routes.py`:
  - in `test_app_routes_and_the_enumeration_agree_exactly__S032_002_DoD1`,
    increment `EXPECTED_ROW_COUNT` by one and drop 5 from the expected
    `EXCLUDED_ROWS` set;
  - `test_no_unbuilt_surface_has_landed__S032_002_DoD1` needs no edit beyond the
    support change. It passes once row 5 no longer flags the built route.
- `backend/tests/test_privacy_audit_export_import.py`: edit the test covering
  S032_005 DoD-1/DoD-6, around lines 385–402. Confirm the function name before
  editing.
  - Replace its row-5 unbuilt guard with a positive check that
    `/api/bootstrap/import` is registered. Keep the `BOOTSTRAP_PATH in matching`
    assertion.
  - Drop the `UNBUILT_SURFACES` import if it is no longer used.
  - Update the module docstring where it calls row 5 unbuilt.

## Interface intent

### Backend

- **In-transaction whole-database import helper** (`services/transfer_import.py`,
  private to the services layer but importable by `services/bootstrap.py`).
  - Takes a connection that is **already inside a transaction** and the raw body.
  - Performs exactly the sequence `import_database` performs today:
    replaceability guard → envelope validation for the `database` granularity →
    memo-scope target check → FTS ensure → registry wipe → vec0 drop → payload write.
    It keeps the `IntegrityError` → `ExportInvalidError(REASON_MALFORMED_PAYLOAD)`
    translation.
  - Never opens or commits a transaction and returns nothing.
  - `import_database` becomes "open a transaction, call the helper". Its public
    signature, behaviour, errors and docstring meaning are unchanged, and the
    docstring is updated to name the helper and its second caller.
- **Restore-from-export service function** (`services/bootstrap.py`).
  - Takes a connection and the raw body, returns nothing. Inside **one**
    `with connection.begin():` it:
    1. re-checks `is_configured` and raises `AlreadyConfiguredError` if
       configured;
    2. creates the schema (`metadata.create_all`);
    3. ensures the FTS tables;
    4. calls the in-transaction import helper.
  - Any error raised inside rolls the whole transaction back, the created DDL
    included.
  - It logs a single `bootstrap` outcome line for success and for each refusal or
    failure, with no content. It mints no session.
- **`POST /api/bootstrap/import`** (`routers/bootstrap.py`, on the existing guarded
  router).
  - Request: a raw JSON object body, typed as a string-keyed mapping exactly like
    the admin import route.
  - Behaviour: calls the restore service function.
  - Response: **204, no body, no `Set-Cookie`**.
  - Errors propagate unhandled to the global `DomainError` handler:
    - 400 `export_invalid`
    - 409 `already_configured` (from the router guard or the service re-check)
    - 409 `database_not_empty`
    - 422 for a non-object body
  - Update the module docstring: two routes now exist, and the import inherits the
    guard by being declared on this router.

### Frontend

- **`restoreExport.ts`**:
  - A small MobX-observable restore state holding:
    - the chosen file (or none);
    - an in-flight flag;
    - the current failure message (or none).
  - A free-function submit taking the state, an `AbortSignal` (or controller, the
    same shape as the create-admin submit), and the navigation seam. It:
    1. reads the chosen file with `readExportFile`;
    2. posts the parsed object with `apiPost` to `/api/bootstrap/import`;
    3. on success calls `documentNavigation.assign("/login")`;
    4. on any failure — an unreadable file or any API error — stores
       `failureMessageOf(error)` and does not navigate.

    It sets the in-flight flag for the duration and ignores an abort the same way
    the create-admin submit does.
  - A setter for choosing a file, which clears any previous failure.
- **`RestoreExportForm.tsx`**: an observer component that renders inside the
  "Restore from an export" list item, in this order:
  1. The static **environment notice**, a Mantine `Alert` or `Text` visible before
     any upload. It must state that credentials and API keys are not included in
     an export, and that the environment (the `.env` file) must be supplied
     separately for the restored instance to reach a model server. The copy must
     contain the literal substrings `API keys` and `.env`.
  2. A **file input** with the accessible label `Export file`, accepting `.json`.
  3. A **`Restore database` button**. It is disabled until a file is chosen, and
     disabled while the request is in flight.
  4. An **inline red `Alert`** (`color="red"`, `role="alert"`) showing the failure
     message when there is one. Never a notification.

  The component owns its `AbortController` and aborts on unmount, mirroring
  `CreateAdminForm`.
- **Offer phase** (`BootstrapPage.tsx`): the existing `List` gains a second
  `List.Item` with the visible heading text `Restore from an export`, which hosts
  `RestoreExportForm`. The "Create a new database" item is unchanged.

## Definition of done

Backend, covered by `backend/tests/test_bootstrap_import.py`. "Real export" means
the following:

- The source database is seeded with at least two admins, one roleplayer and at
  least one character owned by a non-first user.
- Every seeded user has a known plaintext password.
- The export is produced by `export_database` from that source.
- The target is the unconfigured, empty file from `db_engine` / `db_settings`.

The DoD items:

- **DoD-1 [test]**: `POST /api/bootstrap/import` with a real export answers 204
  with an empty body.
- **DoD-2 [test]**: After DoD-1, the target's `users` table holds exactly the
  source's users. That means the same ids, usernames, roles and password hashes,
  with both admins present. The seeded character exists in the target with the
  same id and owner.
- **DoD-3 [test]**: The 204 carries no `Set-Cookie` header, and the target's
  `auth_sessions` table is empty afterwards.
- **DoD-4 [test]**: After a restore, signing in through the existing login route
  works with the source credentials. A restored admin who is **not** the first
  admin succeeds, and so does the roleplayer. A wrong password for a restored
  user is still refused.
- **DoD-5 [test]**: After a restore, `GET /api/health` reports the instance as
  configured. `POST /api/bootstrap/create` and `POST /api/bootstrap/import` both
  answer 409 `already_configured`.
- **DoD-6 [test]**: An invalid envelope (for example a non-`database`
  granularity, or a missing required envelope field) answers 400
  `export_invalid`. Afterwards the target file contains **no `users` table**,
  `is_configured` is false, and a subsequent `POST /api/bootstrap/create` succeeds
  with 201.
- **DoD-7 [test]**: A real export whose payload is altered to violate a database
  constraint (for example a duplicated `users` row) answers 400 `export_invalid`.
  This failure happens after the schema was created inside the transaction.
  Afterwards the target file contains **no `users` table** and `is_configured` is
  false, which shows the DDL was rolled back with the import.
- **DoD-8 [test]**: On an instance already configured through the create path,
  `POST /api/bootstrap/import` with a real export answers 409
  `already_configured`. The users table still holds only the original admin.
- **DoD-9 [test]**: A JSON body that is not an object (for example an array)
  answers 422.
- **DoD-10 [test]**: The restore service function raises `AlreadyConfiguredError`
  and changes nothing when it is called directly on a configured connection,
  without going through the router guard.
- **DoD-11 [test]**: Across a successful restore and a failed one, no log record
  contains any seeded username or plaintext password. At least one log record from
  the bootstrap logger is emitted for the successful restore.
- **DoD-12 [test]** (verifier gate, no new test): the full backend suite passes,
  including the unchanged `test_transfer_import_database.py` and the admin
  database-import router tests. This shows `import_database`'s behaviour is
  preserved. `mypy app` and `ruff check .` are clean.

Frontend, covered by `frontend/tests/bootstrap/RestoreExport.test.tsx`. Health is
stubbed so the page reaches the offer phase.

- **DoD-13 [test]**: In the offer phase both choices render: "Create a new database"
  and "Restore from an export".
- **DoD-14 [test]**: The environment notice is visible before any file is chosen,
  and its text contains `API keys` and `.env`.
- **DoD-15 [test]**: The `Restore database` button is disabled until a file is
  chosen in the `Export file` input.
- **DoD-16 [test]**: Choosing a valid JSON file and pressing `Restore database`
  sends exactly one `POST` to `/api/bootstrap/import`, whose JSON body equals the
  file's parsed contents. On a 204 the app calls
  `documentNavigation.assign("/login")`.
- **DoD-17 [test]**: While the request is pending, the `Restore database` button
  is disabled.
- **DoD-18 [test]**: A 400 `export_invalid` response shows an inline alert
  (`role="alert"`) and does not navigate. The alert's text is whatever
  `failureMessageOf` produces for that error.
- **DoD-19 [test]**: A file that is not valid JSON shows an inline alert, sends no
  request and does not navigate.
- **DoD-20 [test]** (verifier gate, no new test): `npm test` passes, including the
  existing bootstrap tests. `npm run typecheck` and `npm run build` are clean.

Live behaviour, recorded by the verifier as requires-live-run:

- **DoD-21 [manual/live]**: Start from a fresh `data/` directory and open
  `/bootstrap/`, then:
  1. choose a whole-database export downloaded from another instance's admin
     Database page and restore it;
  2. confirm the browser lands on `/login`;
  3. confirm signing in as any of the export's admins reaches the admin entry;
  4. reload `/bootstrap/` and confirm it shows the already-configured refusal.

Privacy-audit enumeration (amended 2026-10-07), covered by the "Update existing"
test files:

- **DoD-22 [test]**: The existing feature-032 privacy-audit tests classify the
  bootstrap import route and no longer guard it as unbuilt. In those tests:
  - `POST /api/bootstrap/import` is enumerated as row 5 with access `public`;
  - row 5 is no longer in `EXCLUDED_ROWS`;
  - the expected row count is one higher than before this plan;
  - the S032_005 DoD-1/DoD-6 test checks positively that the route is registered.

  No other assertion in those files is weakened, removed or loosened, and the full
  backend suite is green (DoD-12).

## Out of scope

- The import machinery itself (plan 031). This plan changes it only by extracting
  the in-transaction helper, with no behaviour change.
- Any partial-granularity import at bootstrap: user, character or session exports
  are refused as `export_invalid`.
- A confirm modal on the bootstrap restore.
- Any preview, count, table list or summary of the export, before or after the
  restore (R5 opacity).
- Signing the operator in automatically after a restore (no cookie, no session).
- Special handling for an export without an administrator.
- Any application-level body-size limit.
- Supplying or validating the environment or `.env` from the UI or the backend.
  The bootstrap screen only states the requirement.
- Changes to the admin Database page's import, the login entry or the auth routes.
- Re-embedding or vector rebuild after the restore (`fast/002`).
- Any privacy-audit edit other than row 5. Other rows, including fast/002's
  row 74, other `UNBUILT_SURFACES` entries and unrelated audit tests, are left
  as they are.
