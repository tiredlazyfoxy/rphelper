# Feature 031 — import-and-id-remapping — outcome

This file lists the architecture changes this feature intends once it ships,
grouped by target file. The architect applies them at finalization.

## `docs/architecture/data-model.md`

- **§"Export / import contract", "Import policy".** Record the import as built
  (plan 031) for the three ACT-002 granularities:
  - Every payload row gets a fresh snowflake from the shared generator. Ids are
    minted per table in ascending old-id order, so the rows' relative order (the
    stream's `ORDER BY id`) survives.
  - Every FK, `messages.related_to` and `memos.scope_id` is rewritten to the new
    id of its target.
  - `user_id` is set to the caller, and so is the `scope_id` of a `scope='user'`
    memo.
  - The payload `users` row is never written (US-136.AC-1).
  - A model pair is kept only if `(model_server_id, model_name)` exists in the
    instance's `models`. Otherwise both columns are nulled.
  - Timestamps and archived state are preserved.
  - The self-reference is written in two passes (insert null, then UPDATE), because
    FKs are immediate.

  **Reason:** the sketch named the mechanism but not the rules for references that
  point outside the payload.
- **Same section: the whole-database import is a deliberate deviation.** It is a
  **REPLACE that preserves ids** (user decision U2, 2026-10-03).
  - It is allowed only on an instance with no users, or exactly one user who is an
    admin. Any other state answers `database_not_empty`.
  - In one transaction it:
    - wipes every `metadata` table (including `auth_sessions` and `translations`);
    - **drops** `memo_vec` / `session_vec` if they exist;
    - inserts the export's rows with their own ids.
  - **Reason:** "mint unconditionally" was written for US-136, which covers
    ACT-002's granularities. A restore onto an empty or replaced instance has
    nothing to collide with, and preserving ids keeps the restored instance
    identical to the source (US-077.AC-2).
  - **Flip condition:** a requirement to *merge* a whole-database export into a
    populated instance.
  - The sentence "There is no empty-target requirement, no 'replace' mode" must be
    narrowed to the ACT-002 granularities.
- **Same section: session import target.** A session export is imported **into a
  character the roleplayer chooses**. `character_id` is that character, and
  `setup_id` is null (user decision U1; US-082). Record this beside the C12
  consequence paragraph.
- **Same section: vectors.** Replace "Re-embedding on import is correct" with the
  posture as built:
  - **No import embeds anything** (U3), so no granularity needs an embedding model.
  - Imported memos and sessions have **no vector until the rebuild** (`fast/002`).
  - The FTS half is kept current: `ensure_fts_tables` runs inside the import
    transaction, and the triggers index the inserts.

  **Reason:** an import must not fail on an instance with no designated model.
  **Consequence to record:** a memo without a vector is now a normal post-import
  state, not only an anomaly. `backend-structure.md`'s "an unembedded memo is
  genuinely an anomaly" sentence needs the same qualifier.
- **Vector tables on a database replace: dropped, not cleared** (orchestrator
  decision, plan 031). A vec0 table's declared dimension belongs to the
  *previous* designation. Dropping both tables inside the replace transaction lets
  024's ensure-on-write re-create them at the then-designated model's
  `embedding_dim` on the next qualifying write.
  - **Why:** a restore never strands the instance in `dimension_mismatch` because
    the restored designation measures a different dimension.
  - **Why nothing is lost:** restored rows have no vectors until the rebuild either
    way.
  - **Why it is safe:** DDL is transactional, so a failed import keeps both tables
    and their rows.
  - **Note for "Vector tables":** dropping them is a legitimate state transition,
    not drift.

## `docs/architecture/backend-structure.md`

- **§Layout.**
  - `services/transfer.py` holds export only (030).
  - **`services/transfer_import.py`** (new, 031) holds validation,
    deserialization, the remap engine, the three roleplayer imports and the
    database replace. **Reason:** the export module stays read-only and auditable
    as such.
  - `models/transfer.py` (new) holds the two import response models.
- **New subsection "The import routes — FEAT-018 (plan 031)".** Both routes are
  owned by `routers/transfer.py`, because routers group by feature:
  - `POST /api/import`: `require_user`; accepts `user` / `character`; answers 200
    `{granularity, character_ids}`.
  - `POST /api/characters/{character_id}/import`: `require_user`; accepts
    `session`; answers 200 `{session_id}`.
- **§"The admin route surfaces", `/api/admin/database`.** Add `POST
  /api/admin/database/import`. It answers **204** and clears the session cookie,
  because every `auth_sessions` row, including the caller's, is gone. The surface
  now has five routes, and this is the first admin-db route that takes a body.
- **§"The JSON id boundary".**
  - Add the second deliberate exception to "routes take pydantic models": the
    import routes take a raw JSON object body, because the envelope is
    column-agnostic. The service's deserializer parses the ids inside it (decimal
    strings only), and responses use `SnowflakeOut`.
  - Update 030's flip condition ("if a second raw-dict route appears, extract the
    serializer"): the deserializer reuses 030's id-column predicate, which is the
    shared mechanism.
- **§"The error model" + per-code status record.** Add two rows:
  - `export_invalid` | **400** | the request body is malformed or incompatible |
    plan 031.
    - `detail` is exactly `{"reason": …}`, one of `not_an_export`,
      `unsupported_version`, `schema_mismatch`, `wrong_granularity` and
      `malformed_payload`.
    - `detail` never carries table, column or row content (R5).
    - It is the first typed 400 for malformed input.
    - A database-import constraint refusal maps to `malformed_payload` and never
      forwards the driver message.
  - `database_not_empty` | **409** | a well-formed request that conflicts with
    instance state, the same shape as `already_configured` | plan 031.
- **R5 note under §"Routers versus services".** `import_database` takes no
  `user_id`; it is the write-side twin of `export_database`. It is reachable only
  from an admin route (and later from `fast/003`'s bootstrap route), and its guard
  lives in the service.
- **§"Database access".**
  - The import's self-reference is solved by insert-then-UPDATE, not by deferring
    FKs or toggling `PRAGMA foreign_keys`. The Sync rebuild remains the one path
    that suspends FKs.
  - The database replace is the one path that drops the vec0 tables, transactionally
    (see `data-model.md` above).

## `docs/architecture/admin-surfaces.md`

- **§"The page's full design — page-level actions" (~L605-613).** Import is
  **delivered** (plan 031) in 030's action group. Its row changes from "file
  picker, then upload" to this sequence:
  1. a file picker;
  2. a red `ConfirmModal` ("Replace the whole database?"), stating that everything,
     including the admin's own account, is replaced and that they will be signed
     out;
  3. the upload;
  4. a redirect to `/login`.

  Failures, including `database_not_empty`, render in their own inline red `Alert`.
  The realizes column should read UC-061 alongside UC-002.
- **Opacity paragraph (~L724-731).** The import shows nothing of the file either:
  no preview, no counts and no table list, before or after.
- **Rebuild index row.** After a restore, the vector tables are absent until the
  next qualifying write or the rebuild re-creates them. Rebuild-after-restore is the
  normal operational step.

## `docs/architecture/workspace-shell.md`

- **User menu section.** It gains **"Import…"** (`IconUpload`), shown to every
  role, beside "Export my data".
  - It takes a `user` or `character` export; the server decides which by the
    envelope.
  - A character import opens the new character.
  - Every successful import reloads both the characters list and `SessionsState`
    (the tree's session level). It also raises one warning that imported material
    won't appear in semantic search until the rebuild.
  - `UserMenu` now receives `CharactersState` and `SessionsState`.
- **Sessions on the character page.** The section gains a section-level
  **"Import session"** button (`IconUpload`).
  - It imports a session export into *this* character, with no setup (US-082).
  - It then re-loads the section list and `SessionsState`.
  - `SessionsSection` now receives `SessionsState`, threaded through
    `CharacterScreen`.

## `docs/architecture/ui-conventions.md`

- **Icon table, "Export / import" row (L124).** Record the `IconUpload`
  placements: the user menu item, the Sessions section button, and the admin
  Database page button.
- **Confirm convention table.** Add the row "Replace the whole database (import)" |
  FEAT-018 | it replaces every row, including the administrator's own account, and
  signs them out. Add the roleplayer imports to "Deliberately NOT confirmed",
  because they are additive and destroy nothing.
- **§"Async feedback".** The post-import coverage warning (`notifyWarning`) is a
  caveat, not a success message. Record it as the worked example that a warning
  attached to a success is permitted, while a success notification is still a
  defect.
- **Gotcha worth recording.** A file input inside a Mantine `Menu.Item` loses its
  change event when the dropdown unmounts. The user menu therefore uses a hidden
  input outside the menu.

## `docs/architecture/frontend-structure.md`

- **§"The API client".**
  - `shared/importFile.ts` adds `readExportFile` and `postExportFile`. The file is
    read as text, parsed client-side, and posted as JSON through the existing
    `apiPost`. There is no FormData and no multipart.
  - It adds a new client code, `client_unreadable_file` (status 0, "The chosen file
    is not a readable export.").
- **§Per-entry responsibilities.**
  - `app` row: user, character and session import are built (plan 031), in
    `app/importUploads.ts`. After an import the effects reload `SessionsState`
    alongside the characters list or the Sessions section.
  - `admin` row: the whole-database import is built.

## `docs/architecture/domain-rules.md`

- **R5.** The import's opacity is as built. The admin import shows nothing of the
  file, and no error `detail` carries payload content.
- **R6.** Note that the database replace deletes every row, including archived
  characters, setups and sessions. It is **not** a per-entity delete path: it is a
  whole-instance restore, admin-only, and allowed only when no other account
  exists. Record this so that R6's "no delete path at all" still reads as true for
  those entities.

## `docs/architecture/deployment.md`

- **~L376 `client_max_body_size 64m`.** FEAT-018's import is now built. The upload
  is a JSON body, not multipart, and it is held fully parsed in memory, so the
  practical bound on an import is this nginx limit. **Flip condition:** an export
  that exceeds it in practice means raising the limit or moving to a streamed
  upload.

## `docs/architecture/quick-reference.md`

- Add the three import routes to the route index.
- Add `export_invalid` (400) and `database_not_empty` (409) to the error-code list.

## Product follow-up (for `/product-spec`, not edited here)

- **FEAT-018's note and US-136 read as if every import merges as new.** The
  whole-database import is now a replace onto an empty or single-admin instance,
  with ids preserved (U2). `/product-spec` should state this for UC-061 and
  US-077.AC-2, so that US-136's "nothing existing is overwritten" is visibly scoped
  to ACT-002's granularities.
- **US-082.AC-1 ("carries no character persona")** is realized as "the export's
  persona does not come along". The imported session is placed under a character
  the roleplayer chooses (U1), so it has that character's persona. `/product-spec`
  may want to reword the criterion to match.

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B1 (the backend spine — `session-stream.md`, `transfer.md`, `backend-structure.md`, `data-model.md`, `domain-rules.md`), B2 (the LLM/search/operations layer — `llm-and-streaming.md`, `search-and-retrieval.md`, `deployment.md`, `admin-surfaces.md`, `overview.md`) and B3 (the frontend layer — `workspace-shell.md`, `frontend-structure.md`, `ui-conventions.md`, `forms-and-lists.md`).
Rejected items: none
Notes: Both `/product-spec` follow-ups it raised are discharged — `UC-061`, `US-077.AC-3` and `US-136`'s `Constraint:` now scope merge-as-new to the roleplayer's three granularities, and `US-082` with `UC-064`'s postcondition now states that an imported session takes the chosen character's persona. The "an unembedded memo is genuinely an anomaly" sentence is qualified: after 031 it is a normal post-import state.
