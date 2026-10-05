# Feature 030 — export-granularities — context

## Goal and boundary

Let material leave the instance as a downloadable JSON file at four granularities
(whole database, one user's own data, one character, one session), each carrying
its own memos. The agreed boundary is `brief.md`; it is not restated here.

- **Delivers (export halves only):** UC-061, UC-062, UC-063, UC-064; US-077.AC-1,
  US-078.AC-1/AC-2/AC-3, US-079.AC-1, US-080.AC-1, US-081.AC-1.
- **Not here:** import in every form, including US-077.AC-2, US-079.AC-2,
  US-080.AC-2, US-082 and US-136, all of which belong to `031`. Bootstrapping from an
  export is `fast/003`. The privacy audit is `032`.
- **Obligation to 031:** the envelope must carry what import needs. That means every
  row with its own `id` and every internal reference present, so that 031 can mint
  fresh ids and remap them (`data-model.md` §"Export / import contract — sketch",
  import policy).

## Build-order assumption

030 is built **after** 017..029. It plans against the schema those features
produce: 017's six nullable configuration columns on `characters` and `sessions`
plus `sessions.rp_language` / `preferred_language`, 023's `translations` table in
`schema.metadata`, and 024's FTS5/vec0 tables in `backend/app/db/search_tables.py`,
outside `schema.metadata`. **The exporter must not name columns.** It reads every row
with a Core `select(<Table>)` over the `schema.*` Table objects, so that every
column, including ones added later, flows through. Table *sets* are explicit;
column lists are not.

## The envelope (feature-wide; consumed by 031)

One JSON object, UTF-8:

| Key | Value |
|---|---|
| `format` | the literal `"rphelper-export"` |
| `version` | the envelope-format version, an int constant in `services/transfer.py`, starting at `1` |
| `granularity` | one of `"database"`, `"user"`, `"character"`, `"session"` |
| `created_at` | UTC ISO-8601 text, the same shape the services' `_now_text()` produces |
| `schema_version` | the registry-shape version, a separate int constant in `services/transfer.py`, starting at `1` |
| `payload` | an object mapping table name to a list of row objects |

- **There is no root-reference header field.** For `user`, `character` and
  `session` the payload's `users`, `characters` or `sessions` list holds exactly one
  row, which is the root. This decision is flagged for 031 in `outcome.md`.
- **The two version constants are kept separate on purpose.** `version` changes
  when the envelope's own shape or serialization rules change. `schema_version`
  changes when `db/schema.py` changes a table's shape. They move independently. No
  schema-version constant exists anywhere else, so `schema_version` is bumped **by
  hand** whenever `db/schema.py` changes shape, as recorded in `outcome.md`.

### Row serialization rules

- **Every column of the selected table is present** in each row object, keyed by
  column name, except where a granularity names an explicit column exclusion
  (`users` at user granularity, below).
- **Id columns become decimal strings.** An integer column is an id column if any of
  these holds:
  - it is part of the table's primary key;
  - it carries a foreign key;
  - its name is `id` or ends in `_id`. This catches the FK-less references
    `memos.scope_id` and 017's `model_server_id`.

  A null id stays null. This matches the `SnowflakeOut` wire rule
  (`backend-structure.md` §"The JSON id boundary") and keeps snowflakes JS-safe.
- **Booleans are JSON booleans. Enum values are their string value. Timestamps are
  the stored text, unchanged. Nulls are null.** Other integers (e.g.
  `models.embedding_dim`) and floats stay JSON numbers.
- **Rows within a table are ordered by primary key.**
- **Payload tables follow foreign-key dependency order**, which is the order of
  `schema.metadata.sorted_tables` restricted to the included tables, so 031 can
  insert parents first.

## Granularity boundaries (decided; user-confirmed 2026-10-03)

| Granularity | Contains | Scoped by |
|---|---|---|
| `database` | every table in `schema.metadata.sorted_tables` **except** the explicit exclusion set {`auth_sessions`, `translations`}, every row, every column (incl. `users.password_hash`, `llm_servers.api_key_ref`) | nothing — admin only |
| `user` | the caller's one `users` row **minus** `password_hash`, `role`, `is_enabled`; their `characters`, `setups`, `sessions`, `messages`; **all** their `memos` (every scope) | `user_id` = caller |
| `character` | the one character; its setups; its sessions (archived included); those sessions' messages; memos with (`character`, the character) or (`setup`, one of its setups) or (`session`, one of its sessions) | `user_id` = caller, plus the root id |
| `session` | the one session; **all** its messages (settled, buried, current-zone); memos with (`session`, this session) **only** | `user_id` = caller, plus the root id |

- **Never exported at any granularity:** `translations` (a derived cache, like
  vectors; this diverges from the sketch and is recorded in `outcome.md`),
  `auth_sessions` (live login tokens), and the FTS5/vec0 tables, which are not in
  `schema.metadata` and so are absent by construction. The exclusion is still
  explicit and tested.
- **Archived characters, setups and sessions are included** at every granularity
  (R6).
- **Credentials:** `llm_servers.api_key_ref` is a `"$ENV_VAR"` pointer and is
  carried as stored. A resolved secret value never appears.
- **Dangling refs are expected:** the `user_id` refs at character and session
  granularity; `character_id` / `setup_id` at session granularity (the C12
  consequence, UC-064); and `model_server_id` / `model_name` everywhere except
  database granularity. 031 decides remap or null.

## Routes (backend, step 003; consumed by steps 005 and 006)

| Route | Guard | Granularity | Router module |
|---|---|---|---|
| `GET /api/admin/database/export` | router-level `require_admin` (existing) | `database` | `backend/app/routers/admin_db.py` |
| `GET /api/export` | `require_user` | `user` | `backend/app/routers/transfer.py` (new) |
| `GET /api/characters/{character_id}/export` | `require_user` | `character` | `backend/app/routers/transfer.py` |
| `GET /api/sessions/{session_id}/export` | `require_user` | `session` | `backend/app/routers/transfer.py` |

Every route answers **200**, `Content-Type: application/json`, and
`Content-Disposition: attachment; filename="rphelper-<granularity>-<UTC timestamp>.json"`.
The filename **never embeds user content**: no name, no title, no id.

## Cross-cutting constraints

- **Ownership is scoped at query level** (R5, `domain-rules.md`). Every
  user/character/session select filters by the authenticated `user_id`. A foreign
  or missing character answers `character_not_found` (404), and a foreign or missing
  session answers `session_not_found` (404). These are the existing errors from
  `app/errors.py`, and there is no 403 for a foreign row. The whole-database export
  is the one deliberately unscoped read; it is admin-only and stays R5-compatible
  through opacity.
- **routers → services → db.** All SQL lives in `backend/app/services/transfer.py`.
  Routers do HTTP only. Services never import `fastapi`.
- **Opacity (US-078, R5, `admin-surfaces.md` ~L724-731).** No viewer, preview,
  search, diff, row count or table-name listing of any export, anywhere. The admin
  page reports only the file's size.
- **No success toasts** (`ui-conventions.md` §"Async feedback"). On success, the
  browser download is the signal. The admin page's size line is inline page text,
  not a notification. Failures in the `app` entry go through `notifyFailure`.
  Failures in the `admin` entry go to the page's inline red `Alert` and never also
  to a notification.
- **No confirm dialogs.** An export is not lossy.
- **Icon:** `IconDownload` (`ui-conventions.md` icon table) on every export
  control, sized like the neighbouring items (`size={16} stroke={1.5}` in menus).
- **Frontend:** TypeScript only. Ids are `string` end to end. MobX classes hold
  observable fields only, and behaviour lives in free functions. There is no
  ESLint, so `npm run typecheck` is the gate.
- **Commands:** from the root `CLAUDE.md` only.

## Files touched across steps

| File | Steps |
|---|---|
| `backend/app/services/transfer.py` | 001 (create), 002 |
| `frontend/src/shared/api.ts` | 004 (consumed by 005, 006) |

## Architecture pointers

- `data-model.md` §"Export / import contract — sketch" (~L853-936). The sketch this
  plan makes concrete.
- `data-model.md` ~L643-658. The memo `(scope, scope_id)` pair that the character
  and session selections filter on.
- `domain-rules.md` R5 (~L383-392) and R6 (~L396-421).
- `admin-surfaces.md` ~L605-613 (page-level actions) and ~L719-731 (opacity).
- `backend-structure.md` §Layout (`routers/transfer.py`, `services/transfer.py`
  pre-named), §"The JSON id boundary", §"Routers versus services", §"The error
  model".
- `frontend-structure.md` §"The API client" (one decode, `ApiError`, 401 →
  `/login`).
- `ui-conventions.md` icon table (L124), and ~L380-423 (no success toasts).
