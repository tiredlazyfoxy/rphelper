# Feature 031 — import-and-id-remapping — context

## Goal and boundary

This feature lets an export made by `030` come back in, at the same four
granularities. The agreed boundary is `brief.md`, which this file does not restate.

- **Delivers (import halves):** UC-061..UC-064; US-077.AC-2, US-079.AC-2,
  US-080.AC-2, US-082.AC-1, US-082.AC-2, US-136.AC-1, US-136.AC-2. Each is cited in
  the `[test]` DoD items that exercise it.
- **Out:**
  - a duplicate-import warning (`brief.md` Out). Importing twice yields two
    disjoint sets of rows, and that is tested as intended behaviour;
  - the bootstrap route that restores onto a fresh instance. That is `fast/003`,
    which will call this feature's database-import service; 031 builds no bootstrap
    route.
- **Brief's open question, answered (U3, user-confirmed):** no import embeds
  anything. No granularity needs an embedding model, and none calls one. Imported
  memos and sessions have no vectors until the administrator's rebuild
  (`fast/002`). The FTS half is kept current (below).

## Build-order assumption

031 is built after `001..030`. `001..017` are built; `018..030` are planned but
unbuilt. This plan binds to the **plans** of the features it builds on:

- **030** (`docs/plans/030.export-granularities/`).
  - **Backend, all in `backend/app/services/transfer.py`:** the envelope, the
    serializer and its id-column rule, the two version constants, the granularity
    value set, the database exclusion set, and the user-granularity `users` column
    exclusion. 031 also uses 030's export routes and `routers/transfer.py`.
  - **Frontend:** `exportDownloads.ts`, `UserMenu` "Export my data", the
    `SessionsSection` "Export" item, and the `DatabasePageState` export fields.

  **Cite 030's names; never re-specify them.** Where 030's plan leaves a name to
  its skeleton, 031's skeleton reads the built code and records the real name in
  `## Skeleton`.
- **024** (`docs/plans/024.embedding-lifecycle/`, D2).
  `backend/app/db/search_tables.py` provides:
  - `ensure_fts_tables(connection)`: idempotent, runs inside the caller's
    transaction, back-fills once when it creates a table;
  - `ensure_vector_tables(connection, dim)`: creates `memo_vec` / `session_vec` at
    the designated dimension when absent, as ensure-on-write;
  - `vector_table_dimension(connection, name)`: answers none when that vec0 table
    is absent;
  - the table-name constants for `memo_fts`, `message_fts`, `memo_vec` and
    `session_vec`.

  The FTS triggers index inserted memo bodies and record-row message text.
- **023**'s `translations` table is in `schema.metadata`. It never appears in a
  payload, and the database replace wipes it.

## Module placement (decided)

- **`backend/app/services/transfer_import.py` (new)** holds all import code:
  validation, deserialization, the remap engine, the three roleplayer imports and
  the database replace.
  - **Why a sibling and not `services/transfer.py`.** `backend-structure.md`
    §Layout pre-names `transfer.py` for "export/import". That module is 030's
    read-only path and already carries the serializer and three selections. Import
    is the opposite operation: it writes, mints ids, and wipes on database replace.
    A sibling module keeps the export module auditable as read-only, and keeps each
    file to one subject.
  - The import module **imports from `transfer.py`**: the format literal, both
    version constants, the granularity value set, the database exclusion set, the
    `users` column exclusion, and the id-column predicate. Nothing in `transfer.py`
    imports the import module.
  - `outcome.md` records the split for `backend-structure.md`.
- **Routes:**
  - `backend/app/routers/transfer.py` (030's) gains the two roleplayer import
    routes.
  - `backend/app/routers/admin_db.py` gains the database import route.
  - Their response models live in `backend/app/models/transfer.py` (new).
- **Frontend:**
  - `frontend/src/shared/importFile.ts` (new) holds the file-read-and-post helper
    both entries use.
  - `frontend/src/app/importUploads.ts` (new) holds the `app` entry's import
    effects. It is the sibling of 030's `exportDownloads.ts`.
  - The admin page's import lives in 030's `admin/databasePageState.ts` and
    `admin/DatabasePage.tsx`.

## Transport (decided)

There is no multipart, and no new Python or npm dependency.

- The browser reads the chosen file as text, `JSON.parse`s it, and posts the parsed
  object as the JSON body with the existing `apiPost`.
- The backend import routes take the raw JSON object (`dict[str, Any]`) as the
  body and validate it themselves.
- A body that is not a JSON object is refused with FastAPI's own 422 before any
  service runs.

## Granularity table sets (what an import accepts)

The payload's key set must be **exactly** the set for its granularity: no table
missing and none extra. This mirrors 030's boundary table (`030/context.md`
§"Granularity boundaries").

| Granularity | Payload tables (exactly) | Root rule | Accepted by |
|---|---|---|---|
| `database` | every `schema.metadata.sorted_tables` table **minus** 030's database exclusion set (`auth_sessions`, `translations`) | — | `POST /api/admin/database/import` only |
| `user` | `users`, `characters`, `setups`, `sessions`, `messages`, `memos` | `users` has exactly 1 row | `POST /api/import` |
| `character` | `characters`, `setups`, `sessions`, `messages`, `memos` | `characters` has exactly 1 row | `POST /api/import` |
| `session` | `sessions`, `messages`, `memos` | `sessions` has exactly 1 row | `POST /api/characters/{character_id}/import` |

- **Rows carry exactly the table's columns.** The one exception is the `users` row
  at `user` granularity. It carries the columns **minus** 030's `users` column
  exclusion (`password_hash`, `role`, `is_enabled`).
- **`llm_servers`, `models`, `auth_sessions` or `translations`** in a non-database
  payload make the key set wrong, so the payload is `malformed_payload`.

## The failure contract (feature-wide)

Step 001 adds two new `DomainError` subclasses in `backend/app/errors.py`:

| Code | Status | `detail` |
|---|---|---|
| `export_invalid` | **400** | exactly `{"reason": <one of the five below>}` and nothing else. No table name, no column, no value, no row content (R5; `deployment.md` redaction rule) |
| `database_not_empty` | **409** | `{}` |

**`detail.reason` is one of a fixed set of five.** Checks run in this order, and
the first one that fails decides the reason:

1. `not_an_export` covers three cases:
   - the body is not an object;
   - any of the six header keys (`format`, `version`, `granularity`,
     `created_at`, `schema_version`, `payload`) is missing, or a key outside them
     is present;
   - `format` ≠ `"rphelper-export"`, or `granularity` is not one of the four.
2. `unsupported_version`: `version` is not an integer equal to 030's envelope
   version.
3. `schema_mismatch`: `schema_version` is not an integer equal to 030's schema
   version. Only an equal value is accepted; newer and older are both refused.
4. `wrong_granularity`: the route does not accept the envelope's granularity.
5. `malformed_payload` covers everything about the payload:
   - `payload` is not an object, or its key set is wrong for the granularity;
   - a table's value is not a list, or a row is not an object;
   - a row has a missing or extra column, or a value of the wrong JSON type;
   - an id is not a decimal-digit string, or is out of the signed 64-bit range;
   - an enum value is outside its set, or a NOT NULL column holds null;
   - the root count is wrong;
   - an internal reference resolves to no payload row where one is required;
   - a memo scope is not allowed at this granularity, or a memo scope target is
     absent;
   - on database import, the database itself refuses a row (FK / UNIQUE / CHECK).

**All validation happens before any write.** The one exception is the database
import's constraint refusals: they happen inside its transaction and roll it back
whole. **Any failure stores nothing.**

## Deserialization (feature-wide; built in 001, used by 002–004)

Deserialization is the inverse of 030's row serialization rules (`030/context.md`
§"Row serialization rules"). The id-column test is **030's id-column predicate**,
so the two directions cannot disagree. Per column:

- **Id column:** a string of decimal digits becomes an `int`. Null stays null.
- **Boolean column:** a JSON boolean.
- **Enum column:** a string in that enum's value set.
- **Other integer column** (e.g. `models.embedding_dim`, `memos.sort_key`): a JSON
  integer. A boolean is not accepted.
- **Text / string column:** a JSON string. Timestamps are stored as text, so they
  are kept verbatim.
- **Null** is accepted only where the column is nullable.

## Remap rules for the three roleplayer granularities (feature-wide; engine in 002, session policy in 003)

- **Every payload row gets a fresh snowflake** from the shared generator
  (`app/ids.py`). Ids are minted per table **in ascending order of the row's old
  id**. The generator is monotonic, so imported rows keep their relative order.
  That matters because the stream reads messages `ORDER BY id`.
- **Every internal reference is rewritten** to the new id of the row it names:
  - each FK column whose referenced table is in the payload;
  - `messages.related_to`;
  - `memos.scope_id` for scopes `character`, `setup` and `session`.

  A reference whose target is not a payload row is `malformed_payload`, unless a
  rule below covers it. A null reference stays null.
- **Out-of-payload references:**
  - every `user_id` becomes **the caller**;
  - a `scope='user'` memo's `scope_id` becomes **the caller**. Only `user`
    granularity allows that scope;
  - at session granularity, `sessions.character_id` becomes the chosen target and
    `sessions.setup_id` becomes null (step 003);
  - `model_server_id` / `model_name` on characters and sessions are **kept only if
    that pair exists in this instance's `models` table**. Otherwise both are
    nulled, which honours the both-or-neither CHECK.
- **At `user` granularity the payload `users` row is never written.** Nothing on
  the caller's account changes (US-136.AC-1). Its id serves only as the value that
  every payload `user_id`, and every `scope='user'` `scope_id`, must equal.
  Anything else is `malformed_payload`.
- **Allowed memo scopes:**
  - `user` granularity: all four;
  - `character` granularity: `character`, `setup` and `session`, each targeting a
    payload row;
  - `session` granularity: `session` only, targeting the payload session.
- **Preserved as stored:** archived state, every timestamp (`created_at`,
  `updated_at`, `last_used_at`, `archived_at`, `settled_at`), `sort_key`, flags and
  text.
- **Insert order** is `schema.metadata.sorted_tables`.
  - **Self-references are two-pass.** `messages` rows are inserted with
    `related_to` null, then one UPDATE per referring row sets it, inside the same
    transaction. This is needed because a buried row's head has a **higher** id (030
    outcome note), and FKs are immediate (`PRAGMA foreign_keys=ON`, nothing
    deferrable).
  - The CHECK `related_to IS NULL OR settled_at IS NULL` holds at both passes.
- **Atomic:** each import is one `with connection.begin():`.
  - `ensure_fts_tables(connection)` is called inside it, **before the first
    insert**, so the FTS triggers index the inserted rows.
  - A roleplayer import never touches `memo_vec` / `session_vec`.

## Database import (feature-wide summary; detail in 004)

**REPLACE, ids preserved (U2, user-confirmed).** It is allowed only when the
instance has **no users**, or **exactly one user, whose role is admin**. Otherwise
it raises `database_not_empty` and nothing changes.

When allowed, it runs in one transaction:

1. ensures FTS;
2. deletes every row of every `metadata` table, including the importing admin,
   their `auth_sessions`, `llm_servers`, `models` and `translations`;
3. **drops** `memo_vec` / `session_vec` when they exist (orchestrator decision).
   024's ensure-on-write re-creates them later at the then-designated model's
   dimension;
4. inserts the payload with its **own** ids.

The service takes **no request user**, so that `fast/003` can call it. It deviates
deliberately from `data-model.md`'s "mint unconditionally" rule, as recorded in
`outcome.md`.

## Wire contract (feature-wide; routes in 005, consumed by 006–008)

| Route | Guard | Accepts | Success |
|---|---|---|---|
| `POST /api/import` | `require_user` | `user`, `character` | **200** `{ "granularity": "user" \| "character", "character_ids": ["<id>", …] }` |
| `POST /api/characters/{character_id}/import` | `require_user` | `session` | **200** `{ "session_id": "<id>" }` |
| `POST /api/admin/database/import` | router-level admin (existing) | `database` | **204**, and the session cookie is cleared |

- **`character_ids`** are the new ids of every imported character, in ascending
  order. A `character` import has exactly one entry, and a `user` import with no
  characters has none. Ids are decimal strings (`SnowflakeOut`).
- **A foreign or missing target character** answers `character_not_found` (404).
  R5 applies: no 403, and no leak of whether the character exists. An **archived**
  target is accepted (R6).
- **Failure bodies** are the standard `{"error": {code, message, detail}}` with the
  codes above.

## Frontend shared facts

- **The unreadable-file failure.** When the chosen file cannot be read, is not
  JSON, or is not a JSON object, the client raises an `ApiError` with:
  - code `client_unreadable_file`;
  - status `0`;
  - message exactly **"The chosen file is not a readable export."**

  This happens before any request. Each entry renders it through its usual error
  path: `notifyFailure` in `app`, the inline red `Alert` in `admin`.
- **Reload scope after a roleplayer import** (orchestrator decision). `SessionsState`
  drives the session level of the character tree, so every successful roleplayer
  import reloads it with `loadSessions`:
  - **user or character import:** reload the characters list (`loadCharacters`)
    **and** `SessionsState`;
  - **session import:** refresh the character page's Sessions section **and**
    reload `SessionsState`.

  A failed import reloads nothing.
- **Ids are strings end to end.** `id: number` anywhere is a defect.
- **MobX classes hold observable fields only.** Behaviour lives in free functions,
  with `runInAction` after `await`.
- **No success toasts** (`ui-conventions.md` §"Async feedback"). A roleplayer
  import raises exactly one `notifyWarning`, the coverage sentence pinned in
  `006.context.md`. That is a caveat about search, not a success message.
- **Icon:** `IconUpload` (`ui-conventions.md` icon table, L124) on every import
  control. It is sized like its neighbours: `size={16} stroke={1.5}` in menus and
  buttons.
- **Confirm:** only the database import, which is destructive, uses
  `shared/ConfirmModal`. Roleplayer imports are additive and are deliberately not
  confirmed (`ui-conventions.md` §"Deliberately NOT confirmed" rationale: they
  destroy nothing).

## Cross-cutting constraints

- **R5.** Every roleplayer import writes only the caller's `user_id`. The target
  character lookup is scoped by `user_id` in the query itself. No error `detail`
  and no log line carries payload content.
- **routers → services → db.**
  - All SQL is in `services/transfer_import.py`.
  - Routers do HTTP only.
  - Services never import `fastapi`.
  - Services take `(connection, generator, user_id, …)`. The database import takes
    `(connection, envelope)`.
- **Backend is fully typed.** `mypy app` and `ruff check .` stay green after every
  step. **Frontend:** `npm run typecheck` stays green. There is no ESLint.
- **Commands** come only from the root `CLAUDE.md`.

## Files touched across steps

| File | Steps |
|---|---|
| `backend/app/services/transfer_import.py` | 001 (create), 002, 003, 004 |
| `backend/app/errors.py` | 001 (consumed by 002–005) |
| `backend/app/services/transfer.py` (030) | 001 (exposes the id-column predicate only) |
| `frontend/src/shared/importFile.ts` | 006 (create; consumed by 007, 008) |
| `frontend/src/app/importUploads.ts` | 006 (create; consumed by 007) |

## Test conventions

**Backend** (from `backend/`):

- pytest, flat `tests/`, test names `test_<behavior>__S031_<SSS>_DoD<n>`.
- Fixtures are `db_settings` and `db_engine`. Each test creates the schema with
  `schema.metadata.create_all`.
- Use snowflake-sized ids (above 2^60) and two users for isolation. Pass in a real
  `SnowflakeGenerator`.
- No monkeypatching. Router tests use `app.dependency_overrides`.
- **Envelopes for tests are produced by 030's exporters** (`export_user`,
  `export_character`, `export_session`, `export_database`) over seeded rows, then
  mutated where a test needs a malformed one. **Expected values come from this
  plan and from the seeded rows, never from calling the import under test.**

**Frontend** (from `frontend/`):

- Vitest/jsdom, `tests/` mirrors `src/`, and each `it` title ends `— DoD-N`.
- `fetch` is stubbed per test with `vi.stubGlobal`, keyed on path and method.
- Components render inside `<AppProviders><MemoryRouter>`.

**Regression rule:** each step lists the existing test files it is known to affect.
If the red-gate run shows a failure in an existing test file that the step does not
list, that is a `SPEC` hand-back. The orchestrator extends that step's Test files;
nobody edits an unlisted file.

## Architecture pointers

- `data-model.md` §"Export / import contract — sketch" (~L853-936), including
  "Import policy".
- `backend-structure.md`: §Layout, §"The JSON id boundary", §"Routers versus
  services", §"The error model" and the per-code status record, §"Transactional
  DDL".
- `admin-surfaces.md` ~L605-613 (page-level actions; Import joins 030's group) and
  ~L719-731 (opacity).
- `ui-conventions.md`: the icon table L124, §"Async feedback", and the confirm
  convention ~L486-548.
- `frontend-structure.md` §"The API client".
- `domain-rules.md`: R5 (~L383-392) and R6 (~L396-421).
- `workspace-shell.md`: the user menu, and the sessions section on the character
  page.
- `deployment.md` ~L376: `client_max_body_size 64m` bounds an import upload.
