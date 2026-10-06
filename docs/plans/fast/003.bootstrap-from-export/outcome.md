# fast/003.bootstrap-from-export — outcome

Intended doc changes, for the architect to apply at finalization.

## docs/architecture/backend-structure.md

- **Section:** "The bootstrap route surface — FEAT-001"
  **Change:** Replace the reserved `POST /api/bootstrap/import` row with the
  as-built route:
  - **204**, no body, **no `Set-Cookie`**;
  - raw JSON-object body, the same as the admin import;
  - errors: 400 `export_invalid`, 409 `already_configured`, 409
    `database_not_empty`, 422 for a non-object body.

  Add **Realizes:** UC-002. State that the restore does **not** sign the operator
  in, unlike the create: no session exists, `auth_sessions` is never restored, and
  the frontend sends the operator to `/login`. Record the asymmetry with the
  create route as deliberate.
  **Reason:** Closes the reservation. The route is built.

- **Section:** "The bootstrap route surface — FEAT-001" (bullets)
  **Change:** Record the one-transaction rule for the restore. The bootstrap
  restore service runs these steps inside a single transaction, so a failed
  restore leaves no tables and the instance stays unconfigured:
  1. re-checks `is_configured`;
  2. creates the schema;
  3. ensures FTS;
  4. runs the whole-database import helper.

  This rests on the transactional-DDL setting.
  **Reason:** The all-or-nothing guarantee is the feature's central design decision.

## docs/architecture/transfer.md

- **Section:** "R5 and the two services that take no `user_id`"
  **Change:** Replace "`import_database` will also be reachable from `fast/003`'s
  bootstrap route (UC-002) when that lands" with the as-built fact. The
  whole-database import is reachable from two routes: the admin import, and
  `POST /api/bootstrap/import`. Both share one in-transaction helper. The admin
  path opens its own transaction around it. The bootstrap path wraps it together
  with schema creation in one transaction. The single-admin guard is in the shared
  helper, so neither caller can skip it. The bootstrap screen keeps the opacity
  rule: nothing of the import is shown.
  **Reason:** The forward reference is now delivered.

- **Section:** "The whole-database replace" (or wherever `import_database`'s
  transaction is described)
  **Change:** Name the extracted in-transaction helper and say that
  `import_database` is "transaction + helper".
  **Reason:** As-built structure.

## docs/architecture/frontend-structure.md

- **Section:** the `bootstrap` entry (Per-entry responsibilities, and the entry's own
  section if it describes the offer phase)
  **Change:** Record the offer phase's second `List.Item`, "Restore from an
  export". It contains:
  - the static environment notice (API keys and `.env` are not in an export);
  - the file picker;
  - the `Restore database` action, with an upload that hands off to `/login`;
  - failures as an inline red `Alert`.

  Note that there is deliberately **no confirm modal**, unlike the admin import:
  the instance is empty and nothing is destroyed. The state lives in
  `bootstrap/restoreExport.ts`, mirroring `createAdminDraft.ts`.
  **Reason:** As-built record and a named asymmetry with the admin import.

## docs/architecture/admin-surfaces.md

- **Section:** "The page's full design" (Import row and its four-step sequence)
  **Change:** Add a one-line cross-reference. The bootstrap restore is the same
  flow without step 2 (the confirm), because it replaces nothing.
  **Reason:** Keeps the two import surfaces' deliberate difference visible from
  both sides.

## docs/architecture/quick-reference.md

- **Section:** route and error-code tables, and the deferrals or `_TBD:` registry
  **Change:**
  - Add `POST /api/bootstrap/import` (204) to the route index.
  - Remove any "UC-002 deferred to fast/003" entry from the deferrals or `_TBD:`
    registry.
  **Reason:** Deferral closed.

## docs/architecture/overview.md

- **Section:** deferrals
  **Change:** Remove the bootstrap-import deferral (UC-002), if it is listed.
  **Reason:** Delivered.

## Observations
