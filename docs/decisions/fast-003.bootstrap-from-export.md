# Decisions — fast-003.bootstrap-from-export
**Stage:** 005.portability · **Feature:** fast/003.bootstrap-from-export

Restoring a fresh instance from a whole-database export at first run (UC-002).
The contracts are `backend-structure.md` "The bootstrap route surface",
`transfer.md` "R5 and the two services that take no `user_id`" and
`frontend-structure.md`'s `bootstrap` entry. Written at finalization
(2026-11-09). The feature's plan numbered its decisions 1–5; **plan "Decision 4"
is `DEC-F003-4`**.

### DEC-F003-1 — Schema creation and the import run in one transaction, through an extracted helper
- **Status:** accepted
- **Stage:** 005.portability · **Feature:** fast/003.bootstrap-from-export · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** How is a restore onto an empty file made all-or-nothing, when the existing whole-database import assumes the tables already exist and opens its own transaction?
- **Decision:** The body of `import_database` is extracted into a public in-transaction helper, `import_database_in_transaction`, which never calls `begin()`. `import_database` becomes "open a transaction + call the helper", public signature and behaviour unchanged. The new `restore_from_export` in `services/bootstrap.py` opens one transaction and runs, in order: re-check `is_configured` (raising `AlreadyConfiguredError`, as the create does) → `metadata.create_all` → the FTS ensure → the helper. The single-admin guard stays inside the helper, so neither caller can skip it.
- **Reason:** SQLite DDL is transactional in this backend, so a failed restore leaves no tables, the instance stays unconfigured and bootstrap is still offered. Transactions are never nested.
- **Lands in:** `backend/app/services/transfer_import.py`; `backend/app/services/bootstrap.py`
- **Cites:** `backend-structure.md` § The bootstrap route surface, § the transactional-DDL setting; `transfer.md` § R5 and the two services that take no `user_id`

### DEC-F003-2 — The restore route signs nobody in
- **Status:** accepted
- **Stage:** 005.portability · **Feature:** fast/003.bootstrap-from-export · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Should `POST /api/bootstrap/import` set a session cookie, as the create route does?
- **Decision:** No. It answers 204 with no body and no `Set-Cookie`. The handler takes the raw JSON object body (as the admin import does), calls the one service function and has no try/except; errors go through the single `DomainError` handler. It sits on the existing bootstrap router, so it inherits the router-level `require_unconfigured` guard.
- **Reason:** No session exists to hand out and the import never restores `auth_sessions`; the operator signs in with the export's own credentials. The asymmetry with the create route is deliberate.
- **Lands in:** `backend/app/routers/bootstrap.py`
- **Cites:** `backend-structure.md` § The bootstrap route surface

### DEC-F003-3 — After the restore the operator is sent to `/login`; the environment notice is static copy
- **Status:** accepted
- **Stage:** 005.portability · **Feature:** fast/003.bootstrap-from-export · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Where does a successful restore land, and how is the operator told that the environment does not travel in an export?
- **Decision:** A 204 hands off to `/login` by document navigation. Before the upload, static copy states that credentials and API keys do not travel in an export and that the environment (`.env`) must be supplied separately for the restored instance to reach a model server. There is no backend field for it.
- **Reason:** The restored users' password hashes and roles travel in the export, so the existing login route authenticates against them with no auth change. The notice is a fact about every export, not about the uploaded file, so it needs no server input.
- **Lands in:** `frontend/src/bootstrap/restoreExport.ts`; `frontend/src/bootstrap/RestoreExportForm.tsx`

### DEC-F003-4 — The restore choice: a second offer item, no confirm modal (plan "Decision 4")
- **Status:** accepted
- **Stage:** 005.portability · **Feature:** fast/003.bootstrap-from-export · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** What does the restore look like on the bootstrap screen, and does it take the admin import's red confirm?
- **Decision:** The offer list gets a second item, "Restore from an export", after "Create a new database". It holds the environment notice, a file picker and a `Restore database` action: the upload goes through `readExportFile` + `apiPost`; a 204 navigates to `/login`; a failure renders an inline red `Alert`; the control is disabled while the request is in flight. **There is no confirm modal.** State and free functions live in `bootstrap/restoreExport.ts`, the UI in `bootstrap/RestoreExportForm.tsx`, mirroring `createAdminDraft.ts` / `CreateAdminForm.tsx`.
- **Reason:** The instance is empty and nothing is destroyed, so the admin import's confirm (whose consequence is "replace the whole database") has nothing to warn about.
- **Rejected:** Reusing the admin import's four-step flow with its confirm — a red warning about destroying data that does not exist.
- **Lands in:** `frontend/src/bootstrap/restoreExport.ts`; `frontend/src/bootstrap/RestoreExportForm.tsx`; `frontend/src/bootstrap/BootstrapPage.tsx`
- **Cites:** `frontend-structure.md` § the `bootstrap` entry; `admin-surfaces.md` § the Import row

### DEC-F003-5 — Accepted consequences, deliberately not special-cased
- **Status:** accepted
- **Stage:** 005.portability · **Feature:** fast/003.bootstrap-from-export · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Which edge states does the restore leave unguarded?
- **Decision:** Four, each accepted:
  - **An export with no administrator** restores, but the instance stays unconfigured, so bootstrap is offered again. Whole-database exports come only from the admin route, so a real one always holds an admin.
  - **An unconfigured but non-empty database** (a `users` table with roleplayers and no admin — only a hand-damaged file produces it) passes the guard and is refused by the import's own single-admin check as 409 `database_not_empty`.
  - **The vector tables are absent after a restore** until ensure-on-write re-creates them; the import's vector-table drop already tolerates their absence. That is a legitimate state, not drift.
  - **No application body-size cap**, as on the admin route; nginx's `client_max_body_size 64m` is the only limit.
- **Reason:** Each state either cannot arise through the product or is already handled correctly by an existing rule; a special case would add code for nothing observable.
- **Lands in:** `backend/app/services/bootstrap.py`; `backend/app/services/transfer_import.py`
- **Cites:** `transfer.md` § the whole-database replace; `deployment.md` § nginx (`client_max_body_size`)

### DEC-F003-6 — The restore's log line carries an outcome token only
- **Status:** accepted
- **Stage:** 005.portability · **Feature:** fast/003.bootstrap-from-export · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** coder (confirmed: user, finalization 2026-11-09)
- **Question:** What does the restore log?
- **Decision:** One `bootstrap outcome=<token>` line: `restored` on success, the `DomainError` code on a refusal (`already_configured`, `export_invalid`, `database_not_empty`), `restore_failed` on any other exception, which is then re-raised. Never a username, password, hash, row count or payload fragment.
- **Reason:** The redaction rule; the token is enough to tell what happened.
- **Lands in:** `backend/app/services/bootstrap.py`
- **Cites:** `deployment.md` § Logging (the redaction rule)

### DEC-F003-7 — A native file input inside `Input.Wrapper`, not Mantine's `FileInput`
- **Status:** accepted
- **Stage:** 005.portability · **Feature:** fast/003.bootstrap-from-export · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** coder (confirmed: user, finalization 2026-11-09)
- **Question:** Which control is the "Export file" picker?
- **Decision:** A native `<input type="file" accept=".json,application/json">` labelled through Mantine `Input.Wrapper`, which renders a real `<label for>`. Not Mantine `FileInput` or `FileButton`.
- **Reason:** The label must resolve to the file input itself, so the control is named "Export file" and found by that name. The code carries no comment for this, so this entry is the record.
- **Lands in:** `frontend/src/bootstrap/RestoreExportForm.tsx`
- **Cites:** `ui-conventions.md` § the accessibility floor

### DEC-F003-8 — `failureMessageOf` is exported from the restore module
- **Status:** accepted
- **Stage:** 005.portability · **Feature:** fast/003.bootstrap-from-export · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** How does the test compute the inline failure text without reading the implementation?
- **Decision:** `restoreExport.ts` exports its `failureMessageOf(error)`, so the test calls it to compute the expected alert text. `shared/` still exports none; every module keeps its own copy.
- **Reason:** The test must bind to the interface, not to a copied literal. Lifting the helper into `shared/` would have edited every existing private copy for one test. The code carries no comment for this, so this entry is the record.
- **Lands in:** `frontend/src/bootstrap/restoreExport.ts`
