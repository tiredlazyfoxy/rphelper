# Feature 030 — export-granularities — outcome

Intended architecture changes after this feature ships, grouped by target file, for
the architect to apply at finalization.

## `docs/architecture/data-model.md`

- **§"Export / import contract — sketch".** Retitle the section to "as built
  (plan 030)" and replace the sketch with the concrete envelope. Changes:
  - The header keys are `format`, `version`, `granularity`, `created_at`,
    `schema_version` and `payload`.
  - There is no root-reference field, because the root is the single row in the
    granularity's root table.
  - Payload tables are in `metadata.sorted_tables` order, and rows are in
    primary-key order.
  - Every column is read by a column-agnostic `select(Table)`.

  **Reason:** the sketch deferred field-level detail to this plan (`brief.md`
  Open questions).
- **Same section, the id serialization rule.** Record that an integer column is
  serialized as a decimal string when it is part of the primary key, carries an FK,
  or is named `id` / `*_id`. Name the FK-less references the name rule exists for
  (`memos.scope_id`, `model_server_id`). Record booleans as JSON booleans, enums as
  their string value, and timestamps as stored text. **Reason:** the export carries
  snowflakes to JS consumers, and FK-less refs are invisible to metadata-only
  detection.
- **Same section, the two version constants.** `version` covers the envelope
  shape and serialization rules. `schema_version` covers the registry shape, and
  **is bumped by hand whenever `db/schema.py` changes a table's shape**. Both live
  in `services/transfer.py`. They are kept separate rather than folded into one,
  because they change independently: a column added to `memos` does not change the
  envelope, and an envelope rule change does not change the schema. **Flip
  condition:** if a hand bump is ever missed in practice, derive `schema_version`
  mechanically (e.g. from the registry) instead.
- **Same section, granularity table.**
  - Drop `translations` from the `user` and `session` rows. `translations` is
    **never exported**: it is a derived cache like the vectors, and it is
    re-creatable on demand. This is a user decision (2026-10-03) and diverges from
    the sketch.
  - The `database` row reads "every table in `metadata` except `auth_sessions` and
    `translations`". `auth_sessions` holds live login tokens.
  - The `user` row carries its `users` row **without `password_hash`, `role` or
    `is_enabled`**. Those columns are administrator-controlled account state, and
    carrying `role` would put a privilege grant in a roleplayer-held file.
  - The `character` row explicitly includes its sessions and their messages,
    archived ones included (user decision 2026-10-03, R6).
- **Same section, "What is never exported".** Widen it from "API keys" to:
  credentials (only `"$ENV_VAR"` pointers travel), `auth_sessions`,
  `translations`, and every FTS5/vec0 table. The whole-database export **does**
  carry `users.password_hash` (Argon2 encoded strings), which is what lets restored
  users sign in (US-077.AC-2). Record this, because a reader will assume hashes are
  stripped.
- **Same section, notes for 031 (import).** Four things the importer must handle:
  - `characters.model_server_id` / `model_name` and the session counterparts are
    carried as stored. Only the database granularity carries the `llm_servers`
    rows they point at, so at every other granularity 031 decides whether to remap
    or null them.
  - At character and session granularity, `user_id` refs point at no payload row.
    At session granularity, `character_id` / `setup_id` also point outside the
    payload (C12).
  - Within `messages`, a buried row's `related_to` points at its head, which has a
    **higher** id. So in id order, the referent arrives after the referrer, and 031
    needs a two-pass insert or deferred FK checking for that self-reference.
  - Every table named in a payload is a `metadata` table, and every row carries
    every column of the exporting instance's registry at its `schema_version`.
- **Memo scope-pair rationale (~L652-653).** Reason 3 now has its as-built
  predicates: character granularity = character, its setups and its sessions;
  session granularity = that session only. Note this alongside reason 3.

## `docs/architecture/backend-structure.md`

- **§Layout.** Mark `routers/transfer.py` and `services/transfer.py` as built
  (plan 030), export half only, with import to follow in 031.
- **§"The admin route surfaces", `/api/admin/database`.** It now has four routes:
  add `GET /api/admin/database/export`, which answers 200 with a JSON file
  attachment. It takes no body, no query and no path id. **Reason:** the
  router-level admin guard covers it with no per-handler declaration.
- **New subsection "The export routes — FEAT-018 (plan 030)".**
  - List `GET /api/export`, `GET /api/characters/{character_id}/export` and `GET
    /api/sessions/{session_id}/export` under `require_user`, owned by
    `routers/transfer.py`. Routers group by feature, not by prefix, which is the
    same reason `stream.py` owns `PATCH /api/messages/{id}`.
  - State the `Content-Disposition: attachment; filename="rphelper-<granularity>-<UTC timestamp>.json"`
    rule, and that **the filename never embeds user content**.
  - Record that these are the codebase's first file-download responses.
- **§"The JSON id boundary".** Record the **one deliberate exception to "routes
  return pydantic models"**: the export routes return a raw `Response`, because
  the envelope is column-agnostic and no static model can describe it. The id
  boundary still holds, because `services/transfer.py`'s serializer stringifies
  ids before the router sees them. **Flip condition:** if a second raw-dict route
  appears, extract the serializer into `models/` as the shared mechanism.
- **R5 note under §"Routers versus services".** `export_database` is the one
  service read that takes no `user_id`. It is reachable only from an admin route
  and stays R5-compatible through opacity (no viewer, search or rendering).
  Record this so a reviewer of "every read takes `user_id`" finds the exception
  stated.
- **Root lookups for export.** The character and session exports fetch their root
  row with their own `id` + `user_id` select inside the export's read snapshot, and
  raise the existing `character_not_found` / `session_not_found` (404 for foreign
  and missing alike). They do not reuse the getters, so that archived roots export
  regardless of the getters' archive filtering. No new error codes.
- **Memory posture.** The export is built and encoded in memory as one response.
  **Flip condition:** an instance whose whole-database export no longer fits
  comfortably in process memory needs a streamed response.

## `docs/architecture/admin-surfaces.md`

- **§"The page's full design — page-level actions" (~L605-613).** Export is
  **delivered** (plan 030). The page-level action group sits beside the Database
  title, and Import (031) and Rebuild index (`fast/002`) join the same group.
- **Opacity paragraph (~L724-731).** Record the as-built behaviour:
  - after a successful export, the page renders a single inline size line (e.g.
    "Export downloaded — 12.3 KB"), formatted 1024-based;
  - it renders no content, table name or row count, which a test asserts;
  - an export failure renders in an inline red `Alert` that is separate from the
    drift report's error, and never as a notification;
  - the size line is inline page text, so it does not break the no-success-toast
    rule.

## `docs/architecture/frontend-structure.md`

- **§"The API client".** It gains `apiDownload(path, signal?)`, the first
  non-JSON call. It reads a blob, saves it through a temporary object URL and an
  `<a download>` anchor, and resolves to `{ filename, size }`. The filename comes
  from `Content-Disposition`, with the fallback `rphelper-export.json`. It shares
  the client's **one** error decode, its 401 → `/login` navigation, and the
  `client_*` codes, which is why it lives in `shared/api.ts` rather than a
  separate module. An abort is not wrapped.
- **§Per-entry responsibilities.** In the `app` row, user/character/session export
  is built (plan 030). In the `admin` row, the whole-database export is built, and
  import is still pending (031).

## `docs/architecture/workspace-shell.md`

- **User menu section.** It gains "Export my data" (`IconDownload`), shown to
  every role. Success is silent, and a failure goes through `notifyFailure`.
- **Character page section.** An Export button (`variant="default"`,
  `IconDownload`) sits beside Archive/Restore and is rendered under the same
  condition, so it is absent on the draft page.
- **Sessions on the character page.** Each session row's overflow menu gains an
  "Export" item, for active and archived rows alike.

## `docs/architecture/ui-conventions.md`

- **Icon table, "Export / import" row (L124).** Record the as-built placements of
  `IconDownload`: the user menu item, the character page button, the session row
  menu item and the admin Database page button.
- **§"Async feedback".** Add the export flows as a worked example of "success is
  silent". In the `app` entry the browser download is the success signal. The
  admin page's size line is page text, not a notification.

## `docs/architecture/domain-rules.md`

- **R5 (~L388-392).** Add a pointer: the whole-database export's opacity is as
  built (plan 030). There is no viewer, preview, search or count surface. The
  admin page reports byte size only.
- **R6 (~L413-415).** Add a pointer: the character and session exports carry
  archived objects (plan 030), as built.

## `docs/architecture/quick-reference.md`

- Add the four export routes to the route index, and `rphelper-export`
  `version` / `schema_version` to the invariants list, with the note that
  `schema_version` is bumped by hand on a `db/schema.py` shape change.
