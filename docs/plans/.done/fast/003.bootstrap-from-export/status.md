# Fast feature 003 — bootstrap-from-export

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-10-07 |

## Files Changed

- `backend/app/services/transfer_import.py` — extracted `import_database`'s body into `import_database_in_transaction`; `import_database` now opens the transaction and calls it
- `backend/app/services/bootstrap.py` — `restore_from_export`: one transaction of guard, `create_all`, FTS ensure, in-transaction import; logs `bootstrap outcome=...` token only
- `backend/app/routers/bootstrap.py` — `POST /api/bootstrap/import` (204, no cookie) and module docstring
- `frontend/src/bootstrap/restoreExport.ts` — restore state, `failureMessageOf`, `chooseRestoreFile`, `submitRestoreExport`
- `frontend/src/bootstrap/RestoreExportForm.tsx` — environment notice, `Export file` input, `Restore database` button, inline red alert
- `frontend/src/bootstrap/BootstrapPage.tsx` — second offer `List.Item` "Restore from an export" mounting `RestoreExportForm`

## Skeleton

### Frozen interface (2026-10-07)

Backend:

- `backend/app/services/transfer_import.py` — `def import_database_in_transaction(connection: Connection, body: object) -> None` — new (stub raises `NotImplementedError`). Public name (no leading underscore) so `services/bootstrap.py` imports it without a private-import smell; the docstring restricts it to the services layer. `import_database(connection: Connection, body: object) -> None` is **unchanged in this skeleton** (still holds its own body). The coder moves the body into the helper, makes `import_database` "`with connection.begin():` + call the helper", and updates its docstring to name the helper and its second caller.
- `backend/app/services/bootstrap.py` — `def restore_from_export(connection: Connection, body: object) -> None` — new (stub raises `NotImplementedError`). The coder adds `from app.services.transfer_import import import_database_in_transaction`. It is left out of the stub because ruff F401 rejects an unused import. No import cycle: `transfer_import` imports `services.transfer`, never `services.bootstrap`. `is_configured` and `create_first_administrator` are untouched.
- `backend/app/routers/bootstrap.py` — `@router.post("/import", status_code=204) def restore_database(body: dict[str, Any], connection: Annotated[Connection, Depends(get_connection)]) -> None` — new. The body is the final one-liner `restore_from_export(connection, body)`. It fails loudly through the service stub. There is no `Response` parameter, because no cookie is set. The module docstring is updated (two routes; import inherits the guard; 204/no cookie; error statuses). `typing.Any` import added.

Frontend:

- `frontend/src/bootstrap/restoreExport.ts` — new:
  - `export type RestoreNavigation = { assign(url: string): void }`. `documentNavigation` from `shared/api` satisfies it.
  - `export class RestoreExportState { file: File | null = null; submitting = false; failureMessage: string | null = null; }` (`makeAutoObservable`, autoBind). This is real, not a stub: observable fields only, the same as `CreateAdminDraft`.
  - `export function failureMessageOf(error: unknown): string` — stub throws. Exported so the test can compute the DoD-18 expected text. `shared/` has no exported `failureMessageOf`, because every existing module keeps a private copy.
  - `export function chooseRestoreFile(state: RestoreExportState, file: File | null): void` — stub throws.
  - `export async function submitRestoreExport(state: RestoreExportState, signal?: AbortSignal, navigation?: RestoreNavigation): Promise<void>` — stub throws. When `navigation` is omitted the coder defaults it to `documentNavigation`. It never rejects once implemented.
- `frontend/src/bootstrap/RestoreExportForm.tsx` — new:
  - `export type RestoreExportFormProps = { state: RestoreExportState; navigation?: RestoreNavigation }`.
  - `export const RestoreExportForm = observer(function RestoreExportForm(props: RestoreExportFormProps): React.JSX.Element)` — stub throws on render.
- `frontend/src/bootstrap/BootstrapPage.tsx` — **not edited by the skeleton.** Mounting a component that throws in the offer phase would break the existing bootstrap tests, so this file keeps its current behaviour. The offer `List` is in this file, so no other file is involved. The coder adds the second `List.Item` with visible text `Restore from an export`, after the "Create a new database" item. Its mount mirrors `CreateAdminMount`: `useState(() => new RestoreExportState())`, then `<RestoreExportForm state={...} />`.

- Caller-compile edits (out of Source-files scope): None.

Gates run: `.venv/bin/python -m mypy app` clean (95 files); `.venv/bin/python -m ruff check .` clean; `npm run typecheck` clean. Tests not run. The feature-032 privacy-audit tests are expected to flag the newly registered `/api/bootstrap/import` until the test-coder applies the row-5 edits.

## Tests

### Tests (2026-10-07)
- `backend/tests/test_bootstrap_import.py` (new) — covers DoD-1..DoD-11 — route + service against a real export (source file seeded with two admins, a roleplayer and a roleplayer-owned character, exported by `export_database`; target = unconfigured `db_engine`): 204 empty body; users (id/username/role/hash) and character (id/owner) equal the source; no `Set-Cookie`, `auth_sessions` empty; login works for the non-first admin and the roleplayer, wrong password refused; health configured + create/import 409 `already_configured`; invalid envelope (`user` granularity, missing `schema_version`, missing `granularity`) 400 `export_invalid` + no `users` table + create 201; duplicated `users` row 400 `export_invalid` + no `users` table (DDL rolled back); 409 on a create-configured instance with only the original admin left; non-object bodies 422; `restore_from_export` called directly on a configured connection raises `AlreadyConfiguredError` and changes nothing (plus an unconfigured control); no seeded username/password in any loguru or `app.*` stdlib record across a failed and a successful restore, and at least one `app.*` bootstrap record on success.
- `frontend/tests/bootstrap/RestoreExport.test.tsx` (new) — covers DoD-13..DoD-19 — through `BootstrapPage` (health stubbed `configured:false`) and directly through `RestoreExportForm` / `restoreExport.ts`: both choices render; notice with `API keys` and `.env` visible before a file is chosen; `Export file` label, `.json` accept, `Restore database` disabled until a file is chosen; exactly one `POST /api/bootstrap/import` with the parsed file as body and `documentNavigation.assign("/login")` on 204; button disabled / `submitting` true while pending; 400 `export_invalid` shows an inline `role="alert"` with `failureMessageOf(error)`'s text, no navigation, no notification, cleared by choosing another file; a non-JSON file shows an inline alert, sends nothing, does not navigate. Failure alerts are told apart from the notice (which may itself be a Mantine `Alert`) by the notice's `API keys` copy.
- `backend/tests/privacy_audit_support.py` (updated, row 5 only) — covers DoD-22 — `EnumeratedRoute(5, "POST", "/api/bootstrap/import", "public", None)` added after row 4; `EXCLUDED_ROWS` now empty; `UNBUILT_SURFACES` row-5 entry **kept** as a shape guard with `/api/bootstrap/import` added to `allowed_paths` (chosen because `test_no_unbuilt_surface_has_landed__S032_002_DoD1` still asserts `[5]`).
- `backend/tests/test_privacy_audit_routes.py` (updated) — covers DoD-22 — `EXPECTED_ROW_COUNT` 73 → 74; expected `EXCLUDED_ROWS` `{5}` → empty set; added positive checks that `POST /api/bootstrap/import` is enumerated as row 5, class `public`.
- `backend/tests/test_privacy_audit_export_import.py` (updated) — covers DoD-22 — in `test_own_export_carries_nothing_of_the_other_user__S032_005_DoD1_DoD6` the row-5 unbuilt guard is replaced by a positive registration check of `POST /api/bootstrap/import`; `BOOTSTRAP_PATH in matching` kept; the residual "no other unenumerated bootstrap-shaped path" check kept via `allowed_paths`; `UNBUILT_SURFACES` import still used (pattern); module and function docstrings updated.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 [verifier gate, no new test], DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓, DoD-17 ✓, DoD-18 ✓, DoD-19 ✓, DoD-20 [verifier gate, no new test], DoD-21 [manual/live, no test], DoD-22 ✓

## Notes & Issues

### Plan amendment, 2026-10-07 (user-approved, before build)

`plan.md` **Test files** gained an "Update existing" list, and the plan gained
**DoD-22 [test]** plus an Out-of-scope line. Reason: the feature-032 privacy-audit
tests model `POST /api/bootstrap/import` as an unbuilt surface (row 5, owner
fast/003). Once this plan lands that route, those tests fail, and so does DoD-12
("full backend suite passes"). The test-coder may now update
`backend/tests/privacy_audit_support.py`, `backend/tests/test_privacy_audit_routes.py`
and `backend/tests/test_privacy_audit_export_import.py`, for row 5 only.
fast/002 is built first and edits the same files to mark its row 74 as built,
so every instruction is relative to row 5, never to absolute values.

### Constraints for the coder and test-coder (existing guards)

These existing guards stay green only if they are respected:

- **`backend/app/services/bootstrap.py`**: AST guards forbid all of the following:
  - `fastapi` and `starlette` imports;
  - int literals in the range 100..599;
  - the names `HTTP_*`, `status_code`, `HTTPException` and `HTTPStatus`;
  - any name containing `cookie`;
  - `Response`;
  - `Table(...)`;
  - `app.config`, `Settings` and `get_settings`.

  The guards also pin the signatures of `is_configured` and
  `create_first_administrator`. The restore service must reach the schema through
  `metadata.create_all` and the existing FTS ensure helper. It must never build a
  `Table(...)` or read settings in this module.
- **Frontend offer phase**:
  - It must not render the text "starting" or "not ready", including in the
    environment notice copy.
  - It must not render an `<a href="/login">`. The hand-off goes only through
    `documentNavigation.assign("/login")`.
  - The accessible names of the restore controls must not contain "create".
    `Export file` and `Restore database` comply.
  - The restore form must come **after** the Create form in DOM order, or must not
    be a `<form>` at all.
- **New `frontend/src/bootstrap/` modules** (`restoreExport.ts`,
  `RestoreExportForm.tsx`) import no CSS.

None of these constraints contradicts the plan as written.

### Coder notes (2026-10-07)

- `Export file` is a native `<input type="file" accept=".json,application/json">` labelled through Mantine `Input.Wrapper` (real `<label for>`), not Mantine `FileInput`/`FileButton`, so the label resolves to the file input itself.
- `restore_from_export` logs `bootstrap outcome=restored` on success, `bootstrap outcome=<DomainError.code>` on a refusal (`already_configured`, `export_invalid`, `database_not_empty`) and `bootstrap outcome=restore_failed` on any other exception; then re-raises.
- Confirmed `_drop_vector_tables` already tolerates absent vec0 tables (checks existence, no `IF EXISTS` needed), so no change there.
