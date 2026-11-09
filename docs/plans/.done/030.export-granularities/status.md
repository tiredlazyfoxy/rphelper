# Feature 030 — export-granularities

| Step | File                               | Status  | Verifier | Date |
|------|------------------------------------|---------|----------|------|
| 001  | `001.transfer-core.md`             | done    | PASS     | 2026-10-05 |
| 002  | `002.owned-selections.md`          | done    | PASS     | 2026-10-05 |
| 003  | `003.export-routes.md`             | done    | PASS     | 2026-10-05 |
| 004  | `004.api-download.md`              | done    | PASS     | 2026-10-05 |
| 005  | `005.admin-database-export.md`     | done    | PASS     | 2026-10-05 |
| 006  | `006.app-export-entry-points.md`   | done    | PASS     | 2026-10-05 |

## Files Changed

### Step 001 — transfer core and whole-database export
- `backend/app/services/transfer.py` — the metadata-driven row serializer (id rule, enum arm), the
  single `select` seam `read_table`, `sorted_tables` key ordering, the envelope builder,
  `export_database`, `encode_envelope`, `export_filename` and `_now_text`

### Step 002 — user, character and session selections
- `backend/app/services/transfer.py` — `export_user` / `export_character` / `export_session`: the
  owner-scoped reads, the exporter's own full-row root lookup on `id` + `user_id`, the three memo
  scope predicates and the raw-`messages` read, all through step 001's reader and snapshot

### Step 003 — export routes and download response
- `backend/app/routers/transfer.py` — `_attachment` (the one download-response seam) and the three
  roleplayer route bodies, each handing the caller's id to its service and returning that response
- `backend/app/routers/admin_db.py` — `export_whole_database`'s body: `export_database(connection)`
  plus the same attachment shape built inline, and the three body-only service imports

### Step 004 — shared file-download helper in the API client
- `frontend/src/shared/api.ts` — `filenameFromContentDisposition`'s quoted-parameter read plus its
  fallback constant, the private `saveBlobAsFile` (object URL → in-document anchor → click →
  remove → revoke, in a `finally`), and `apiDownload`'s body: the `same-origin` GET, the
  `decodeErrorResponse` / `mapFetchRejection` reuse and the `Blob` read whose only output is a
  byte count. The module's ten pre-existing exports are untouched.

### Step 005 — admin Database page: Export action and size line
- `frontend/src/admin/databasePageState.ts` — `exportDatabase`'s body (aborted-signal early
  return, the exporting/clear write, the `apiDownload` call, the size-or-message write, back to
  idle) with the private `DATABASE_EXPORT_PATH`, and `formatByteSize`'s 1024-based B/KB/MB arms
  with their two threshold constants
- `frontend/src/admin/DatabasePage.tsx` — `startExport` now calls `exportDatabase(state,
  currentSignal())`; the import of `exportDatabase` is the only other change

### Step 006 — app entry points: own data, character, session
- `frontend/src/app/exportDownloads.ts` — the three path builders (`/api/export`, and the two
  id-bearing routes, each interpolating its argument verbatim) plus `runExport`'s body: `await
  apiDownload(path)`, the private `isAbortRejection` guard — widened past the house
  `instanceof Error` form to match any non-null object whose `name` is `AbortError`, so a
  `DOMException` abort (what `fetch`/`AbortSignal` and `apiDownload`'s post-read re-check raise,
  and not an `instanceof Error` in jsdom or browsers) stays silent alongside a plain `Error`
  named `AbortError` — and the one `notifyFailure`
  call for every other thrown value. Free functions only, no MobX class, no
  `@mantine/notifications` import; the resolved `DownloadResult` is discarded (opacity)
- `frontend/src/app/UserMenu.tsx` — `onExportMyData` is now
  `void runExport(ownDataExportPath())`; the `./exportDownloads` import is the only other change
- `frontend/src/app/CharacterScreen.tsx` — `onExport` now reads the screen's
  `state.characterId`, sets `exporting`, and clears it in a `finally` on the `runExport` promise
  (so both outcomes clear it); plus the `./exportDownloads` import
- `frontend/src/app/SessionsSection.tsx` — the row menu's Export `onClick` is now
  `void runExport(sessionExportPath(session.id))` with that row's id; plus the
  `./exportDownloads` import

## Notes & Issues

- Step 001: the id rule's bare-reference name is derived (`_ID_NAME = _ID_SUFFIX.removeprefix("_")`)
  rather than written out, so the module still spells no column name outside the two exclusion
  constants. The primary-key arm reaches the same name for every table in `schema.metadata`.
- Step 002: the character granularity gets its sibling ids from the `setups` / `sessions` rows it
  has already read (`_row_ids`, key name from `table.primary_key`) rather than from an `in_`
  subquery, which keeps `read_table` the module's only `select` and makes "an empty id list
  contributes no term" explicit — with no sessions, the `messages` read is skipped entirely and the
  key is still present as an empty list.
- Step 003: both routers build the attachment independently, as frozen, and each sets exactly one
  header — `Content-Disposition: attachment; filename="<export_filename(envelope)>"`. Starlette adds
  only `content-type` and `content-length`, so nothing derived from the payload reaches the headers.
  `app/routers/admin_db.py` now holds **zero** `ast.Raise` nodes (007 D13, checked by walking the
  module's AST), and `app/main.py` was left exactly as the skeleton delivered it.
- Step 004: the anchor is appended to `document.body` before the click and removed in a `finally`,
  because a detached element's `click()` does not bubble — a document-level listener (the second
  observation route `004.context.md` allows) only sees it while it is in the document. jsdom emits
  its "Not implemented: navigation to another Document" virtual-console line on that click; that is
  jsdom declining the download, not an error from the helper, and no idiom avoids it.
- Step 004: besides the `mapFetchRejection` abort passthrough (which mirrors `apiRequest`),
  `apiDownload` re-checks `signal.aborted` after the body read and rethrows the signal's own reason
  there. It is the guarantee that an abandoned call saves no file and creates no object URL even
  when the transport resolved anyway; the thrown value is the caller's reason, so it is still
  unwrapped and still not an `ApiError`.

## Ultra phase

- orient: done 2026-10-05
- harvest: done — docs/.cache/ultra/030.export-granularities/harvest.md (1 report, incl. the sweep)

### Orchestrator decisions at harvest (030)

The sweep found **nine amendment sites across four delivered test files, none of them in any
step's Test files**, plus eight factual corrections to the plan. Several of those guards were
planted deliberately by earlier features to assert the **absence** of exactly what 030 adds, so
flipping them is the designed hand-off, not a regression.

1. **Step `003`'s Test files are extended by `backend/tests/test_configuration_router.py`.** Add the
   **three transfer routes** — `("/api/export","GET")`,
   `("/api/characters/{character_id}/export","GET")`, `("/api/sessions/{session_id}/export","GET")`
   — to `LATER_FEATURE_ROUTES`. **Do not add the admin-db export route**: `admin_db` pre-dates the
   configuration router, so its routes legitimately come *before* it and the allow-set covers only
   what follows.
2. **Step `003`'s Test files are also extended by `backend/tests/test_admin_db_router.py`**, at two
   sites: `EXPECTED_OPERATIONS` gains `("GET", f"{PREFIX}/export")` (and the test's
   "only the three routes" title/docstring need rewording), and
   `test_router_declares_no_query_parameter_and_no_non_table_key__DoD3` must widen its branch so
   `/export` is treated like `/tables` — it has no path parameter, so it currently falls into the
   `else` arm and fails `path_names == ["table_name"]`.
3. **Step `005`'s Test files are extended by `frontend/tests/admin/databasePage.test.tsx` and
   `frontend/tests/admin/databaseActions.test.tsx`.** Five clauses in the first and one in the
   second assert that **no control named Export/Import/Rebuild exists**, and one of them
   (`databasePage.test.tsx:907`, "no control outside the report table — no header action bar")
   asserts the absence of the very action group 030 adds. The repair is to **narrow** the
   out-of-scope regex to `import` / `rebuild` / `re-index` only — so the guard keeps protecting
   what has **not** shipped — and to replace the "no control outside the table" clause with one
   that permits exactly the Export action group and nothing else. Both files also carry an
   `ALLOWED_FIELDS` list pinning `DatabasePageState`'s observable fields (two independent copies,
   one per file); both need step 005's three new field names. **Never widen the regex to permit
   Import or Rebuild** — 031 and `fast/002` own those and their guards must stay armed.
4. **`sorted_tables` order is authoritative over the DoD prose.** The real order is
   `['llm_servers','users','auth_sessions','characters','memos','models','setups','sessions','messages','translations']`
   — a topological sort, so **`memos` comes before `setups`/`sessions`/`messages`**. Step 002's
   DoD-1 lists the user payload as "users, characters, setups, sessions, messages and memos, in
   `sorted_tables` order" and DoD-12 as "sessions, messages and memos"; both sequences contradict
   the rule they cite. `context.md`'s rule wins ("the order of `schema.metadata.sorted_tables`
   restricted to the included tables"), and the DoD enumerations are **set listings written in
   reading order, not orderings**. Tests assert set equality plus the ordering **computed from
   `metadata`**, never a hard-coded sequence. Real orders: user → `users, characters, memos,
   setups, sessions, messages`; character → `characters, memos, setups, sessions, messages`;
   session → `memos, sessions, messages`.
5. **Step 001 DoD-7's enum arm tests the wrong column.** `memos.scope` returns a plain `str`, so it
   exercises no enum conversion; `users.role` returns a `Role` **StrEnum member**. The clause's
   `memos.scope` assertion stays true and stays, but the **enum** behaviour must additionally be
   covered on `users.role`, which only appears at **database** granularity (it is dropped from the
   user export).
6. **Step 001 DoD-4 names a table that does not exist.** There is no `session_fts`. The real 024
   tables are `memo_fts`, `message_fts`, `memo_vec`, `session_vec`; assert those four. The clause's
   intent — no FTS/vec table appears — holds either way, since none is in `metadata`.
7. **Step 004 needs no refactor of the client's decode.** `shared/api.ts` already exports
   `decodeErrorResponse` and `mapFetchRejection` as public functions (019 D10, consumed by
   `shared/sse.ts`), so the blob path **reuses** them and DoD-9 is satisfied by not touching them.
   That removes the step's main regression risk.
8. **Two stale descriptions in the plan's own context, corrected:** `CharacterScreen.tsx`'s action
   `Group` holds **no Save button** (018 step 009 removed it), so the Export button simply follows
   Archive/Restore's existing render condition; and `schema.py` exports a fourth non-Table
   selectable, `buried_messages`, which 001's context does not name — harmless, and it confirms the
   `sorted_tables` walk never meets it. Also: `model_server_id` exists on **two** tables
   (`characters` and `sessions`), and `messages.related_to` is an id caught only by the FK arm of
   the id rule — both worth covering in DoD-6.
- skeleton: done — steps 001, 002, 003, 004, 005, 006
- tests: done — steps 001..006 (approved deviations: step 003 amends
  `test_configuration_router.py` ×1 and `test_admin_db_router.py` ×2 per decisions 1 and 2;
  step 005 amends `databasePage.test.tsx` ×6 and `databaseActions.test.tsx` ×2 per decision 3.
  The amendments **narrow** the out-of-scope guards to `import` / `rebuild` / `re-index` and
  replace the "no header action bar" clause with one permitting exactly the Export group — a
  stray second outside control still fails it, and a new `OUT_OF_SCOPE_ROW_ITEM` keeps the full
  regex armed for row menus. Import and Rebuild stay guarded for 031 and `fast/002`.
  No test-coder had a shell, so the red gate carries the lint and typecheck risk.)
- red-gate: **FAIL (run 1) — Fault TEST on steps 001, 002, 003, 005, 006.** Backend **4354
  collected / 26 failed / 42 errors**; frontend **4193 collected / 85 failed**. mypy, ruff and
  `npm run typecheck` all clean — which closed the unexercised lint/typecheck gap across all eleven
  new test files and the four amendments. Four faults:
  1. **Steps 001/002 — the seed violates a real CHECK constraint.** Both files' `_insert_character`
     and `_insert_session` accept `model_server_id` and forward it without `model_name`, but
     `db/schema.py` holds the pair both-NULL or both-non-NULL
     (`ck_characters_model_both_or_neither`, and the same on `sessions`). The fixtures die at setup,
     so **all 42 cases ERROR before any assertion** and 25 tagged DoD items exercise nothing.
     Consequence: the `settle()` seeding path was never reached, so its no-FTS/no-vec/no-designated-
     model posture is **still unverified**, not cleared.
  2. **Step 003 — decision 2 and the harvest sweep both missed two more delivered guards.**
     `test_admin_db_router.py`'s **DoD-14** block holds
     `test_route_surface_has_no_rebuild_export_import_or_vector_route__DoD14` and
     `test_out_of_scope_routes_do_not_exist__DoD14`, which assert the absence of exactly the route
     030 adds. They must be narrowed the way decision 3 narrowed the frontend ones — keeping
     **rebuild**, **import** and the vector route armed while admitting
     `GET /api/admin/database/export`.
  3. **Step 005 — two vacuous clauses.** DoD-3's and DoD-4's "after a successful export" halves
     click Export, then assert only absences; the click's seam throws, so they are identical in
     outcome to their already-accepted "before" twins and would pass against an implementation that
     does nothing.
  4. **Step 006 — three vacuous clauses, and a correction to my own record.** The DoD-7 success
     clause in each of the three component files asserts only silence after a click. **My "Notes
     carried from the skeletons" claim that "every click seam throws, so an absence-shaped clause
     cannot pass vacuously" is wrong for a React event handler**: React swallows the throw, so the
     protection holds only for clauses that also assert the request reached `fetch` (which is why
     DoD-8's dialog clauses are correctly red). Recorded as a correction, not a quibble — it is the
     reasoning I used to accept those clauses.

  **Confirmed and not re-opened:** the accepted true-red (step 003's `__DoD13` AST clause failing on
  exactly one `ast.Raise`, the `export_whole_database` stub) and DoD-3's nonexistent "session title"
  column. **The narrowing check passed on the frontend** — the out-of-scope regexes still match
  `import`/`rebuild`/`re-index`, `OUT_OF_SCOPE_ROW_ITEM` still rejects Export in a row dropdown, and
  the replacement clause's exact-array equality still fails on a stray second outside control. All
  three frontend guards and all 137 other frontend files stayed green. Also: there are **eleven**
  new test files, not nine — an arithmetic slip in my brief, not an out-of-scope file.
- red-gate: **PASS (run 2)** — backend **4353 collected / 66 failed / 0 errors** (round 1's 42
  fixture errors gone; 4354 → 4353 is the one intended parametrize removal), **65/66 failures
  `NotImplementedError`** plus the one accepted `ast.Raise` true-red. Frontend **4193 / 90 failed**,
  7 files — exactly the seven export files; the same 137 others green, both amendment sites
  included. mypy, ruff and `npm run typecheck` all clean, re-run from scratch because neither
  test-coder could.
  **All five previously vacuous clauses now FAIL** — the discrimination round 1 found missing.
  **Two things round 1 could only reason about are now confirmed empirically:** `settle()` on a
  database with no FTS/vec tables and no designated embedding model **degrades rather than raising**,
  and the seed really leaves **two buried rows whose `related_to` points at the head**, which is
  itself in the row set — so step 002 DoD-10 is provable. And the narrowed backend guard was
  replicated over synthetic routes: `rebuild`, `import`, `vector`, `vec0` and `POST .../export` all
  still **reject**; `export` is admitted on **exactly one** path. Narrowed, not disarmed.

### Accepted true-red in a delivered file (030 step 003)

`backend/tests/test_admin_db_router.py`'s
`test_router_issues_no_sql_opens_no_transaction_and_translates_no_error__DoD13` runs an AST over
the **whole** of `app/routers/admin_db.py` and asserts there is **no `ast.Raise` node anywhere in
the module**. The step-003 skeleton's `export_whole_database` body is `raise NotImplementedError`,
so that delivered test **fails at the red gate** and passes again only once the coder fills the
body.

Expect it; do not fault it. It is the same shape as 028's stubbed `get_tool_registry`, and it is
not one of decision 2's two amendment sites — the test is right and the stub is temporary. **At the
verify run it must be green again**; a failure there afterwards is a `CODE` fault (most likely the
coder left a `raise` in that router, which 007's D13 forbids — the 404s come from the service
through the one `DomainError` handler).

### DoD-3's "session title" has no column (030 step 003)

`db/schema.py`'s `sessions` table has **no `title` column** — a session is labelled by its
character, its setup and its start time. Step 003 DoD-3 asks for "a character and a session seeded
under a distinctive name and title". The test-coder bound the distinctive string to the
**session-scope memo body** instead (plus the setup name and every seeded id) and asserts all of
them absent from the `Content-Disposition` header. The clause's intent — no user content in the
filename — is intact, and this is a wording slip in the DoD rather than a spec conflict, so it is
adjudicated here rather than handed back.

### Notes carried from the skeletons (030)

- **Step 005's three frozen field names are `exportStatus`, `exportSizeBytes`,
  `exportErrorMessage`.** Both delivered `ALLOWED_FIELDS` lists are alphabetical and become
  `["applyingTable", "errorMessage", "exportErrorMessage", "exportSizeBytes", "exportStatus",
  "rows", "status"]` — two independent copies, in `databasePage.test.tsx` and
  `databaseActions.test.tsx`.
- **Every click seam in steps 005 and 006 throws rather than no-ops.** Deliberate: a silent handler
  would let the "no confirm dialog appears" and absence-shaped clauses pass against the skeleton; a
  throw cannot.
- **Step 003's `-> Response` return annotation is load-bearing** — FastAPI skips response-model
  generation for it, and the envelope is column-agnostic so no model can describe it. DoD-9's
  "non-numeric path id is 422 before the service runs" is already mechanically true at the
  declaration level, because `SnowflakeIn` makes the OpenAPI parameter an integer.
- **Step 003 also corrected `admin_db.py`'s module docstring** ("Three routes … no rebuild, export
  or import route anywhere on this router") to say four routes while keeping the still-armed half:
  there is still no rebuild and no import route. 031 and `fast/002` own those.
- **Step 004 is append-only** — 38 insertions, 0 deletions in `shared/api.ts`. `apiRequest`,
  `apiGet`, `apiPost`, `decodeErrorResponse` and `mapFetchRejection` are byte-identical, so DoD-9
  holds by construction.
- **The character Export button needs no new predicate** — it sits inside the existing action
  `Group`, which is only reached after the draft-page and loading/not-found/failed early returns.
  That satisfies DoD-4 and DoD-5 structurally.
- **The session row dropdown now holds two items** for the first time (`Archive`/`Restore` plus
  `Export`), reached via the `Actions for <label>` trigger whose label is the formatted start,
  never the id.

## Skeleton

### Step 001 — frozen interface (2026-10-05)

All in `backend/app/services/transfer.py` (new file, the step's only Source file). Bodies
`raise NotImplementedError` except `_reading`, which is noted below.

Types and constants — the values **are** the freeze:

- `ExportGranularity = Literal["database", "user", "character", "session"]` — new
- `JsonScalar = str | int | float | bool | None` — new
- `ExportRow = dict[str, JsonScalar]` — new
- `ExportPayload = dict[str, list[ExportRow]]` — new
- `EXPORT_FORMAT: Final[str] = "rphelper-export"` — new
- `ENVELOPE_VERSION: Final[int] = 1` — new (the envelope's own shape version)
- `SCHEMA_VERSION: Final[int] = 1` — new (the registry-shape version; moves independently)
- `DATABASE_EXCLUDED_TABLES: Final[frozenset[str]] = frozenset({"auth_sessions", "translations"})` — new
- `class ExportEnvelope(TypedDict)` — new — keys exactly `format: str`, `version: int`,
  `granularity: ExportGranularity`, `created_at: str`, `schema_version: int`,
  `payload: ExportPayload`, declared in that order

Functions:

- `serialize_row(table: Table, row: Row[Any], *, drop_columns: Collection[str] = ()) -> ExportRow` — new
- `read_table(connection: Connection, table: Table, where: ColumnElement[bool] | None = None, *, drop_columns: Collection[str] = ()) -> list[ExportRow]` — new
- `ordered_table_names(included: Collection[str]) -> list[str]` — new
- `build_envelope(granularity: ExportGranularity, payload: ExportPayload) -> ExportEnvelope` — new
- `export_database(connection: Connection) -> ExportEnvelope` — new
- `encode_envelope(envelope: ExportEnvelope) -> bytes` — new
- `export_filename(envelope: ExportEnvelope) -> str` — new
- `_now_text() -> str` — new (private; same shape as the other services')
- `_reading(connection: Connection) -> Iterator[None]`, `@contextmanager` — new (private)

Notes on the freeze:

- **`_reading` is the one implemented body.** A `@contextmanager` whose body raises cannot be
  entered by a `with`, so stubbing it would make every other stub unusable and would block the
  red gate. It is the five-line `_reading` the harvest quotes verbatim (`memos.py:364-372`):
  `opened_here = not connection.in_transaction()`, `yield`, roll back in `finally` when opened
  here. No export behaviour lives in it.
- **`drop_columns` is on both `serialize_row` and `read_table`.** Step 002 reads its `users` row
  through `read_table` (the one `select` seam), so the exclusion has to forward through the
  reader; a `Collection[str]` default of `()` accepts a frozenset, set, tuple or list.
- **`read_table`'s `where: ColumnElement[bool] | None`** carries step 002's owner-scoped and
  id-scoped predicates unchanged — comparisons, `and_`/`or_` combinations and `in_` subqueries
  all type as `ColumnElement[bool]` (the project idiom, `services/memo_chain.py`,
  `services/search/ports.py`). Step 002 adds no statement building of its own.
- **Order comes from the registry, not a literal.** `ordered_table_names` takes names and
  returns names, so both step 001's `sorted_tables` walk and step 002's three payloads order
  their keys through the same helper. No module constant lists table order.
- **Names left free for step 002:** `export_user`, `export_character`, `export_session`, and the
  two user-granularity constants (tables not user material, and the dropped `users` columns) —
  `DATABASE_EXCLUDED_TABLES` is named for its granularity precisely so step 002 can add
  `USER_EXCLUDED_TABLES` / `USER_EXCLUDED_COLUMNS` beside it without collision.
- **`ExportEnvelope` is a `TypedDict`**, the first in the backend: the envelope must stay a plain
  JSON mapping (it is dumped directly and read by 031), and a `TypedDict` freezes its key names
  and value types without turning it into a model. `Literal` aliases, `Final` constants and the
  alias-plus-docstring style follow `services/context.py` and `db/sync.py`.
- `app.db.search_tables` is not imported; no column name appears anywhere in the module except
  inside the two exclusion-constant string literals.
- Caller-compile edits (out of Source-files scope): None.
- Gates from `backend/`: `.venv/Scripts/python -m mypy app` → clean (91 files);
  `.venv/Scripts/python -m ruff check .` → clean. pytest not run.

### Step 002 — frozen interface (2026-10-05)

All in `backend/app/services/transfer.py` (changed — the step's only Source file). Step 001's
surface is untouched: no constant, signature, docstring or body of its nine functions, its
`ExportEnvelope`, its four aliases or its seven constants was modified. Bodies `raise
NotImplementedError`.

Constants — the values **are** the freeze:

- `USER_EXCLUDED_TABLES: Final[frozenset[str]] = frozenset({"auth_sessions", "translations"})` — new
- `USER_EXCLUDED_COLUMNS: Final[frozenset[str]] = frozenset({"password_hash", "role", "is_enabled"})` — new

Functions (inserted after `export_database`, before `encode_envelope`):

- `export_user(connection: Connection, user_id: int) -> ExportEnvelope` — new
- `export_character(connection: Connection, user_id: int, character_id: int) -> ExportEnvelope` — new
- `export_session(connection: Connection, user_id: int, session_id: int) -> ExportEnvelope` — new

Notes on the freeze:

- **Ids are `int` at the service boundary**, matching `services.characters.get_character` and
  `services.sessions.get_session` (`connection, user_id, character_id`). The decimal-string id
  rule is a *serialization* rule and lives inside `serialize_row`; it never reaches a parameter.
- **`USER_EXCLUDED_TABLES` is a separate constant from `DATABASE_EXCLUDED_TABLES` despite the
  identical value.** The two granularities justify their exclusions differently and may diverge,
  and DoD-5's classification guard binds to the user-granularity constant by name. Both names are
  granularity-qualified, so they coexist as step 001 planned.
- **Payload order is bound to `metadata`, not to any literal.** All three bodies must derive their
  key order by passing their table-name set to step 001's `ordered_table_names`, which reads
  `schema.metadata.sorted_tables`. No module constant in this file lists a table order, and none
  was added. Per `## Ultra phase` decision 4, the real orders are user → `users, characters,
  memos, setups, sessions, messages`; character → `characters, memos, setups, sessions,
  messages`; session → `memos, sessions, messages` — the coder must not hard-code any of them,
  and the DoD-1 / DoD-12 enumerations are set listings in reading order, not orderings.
- **No private helper is frozen.** The three memo predicates, the root-row lookup and the
  per-granularity payload assembly are left to the coder. A private helper no test can bind to
  buys the contract nothing and would pre-commit a decomposition (one memo-predicate builder vs.
  three, a shared root-row reader vs. two inline selects) that may not fit the implementation.
  The frozen surface is the five names above; everything else in the module stays step 001's.
- **No new import was added.** The three signatures need only `Connection` (step 001 imports it)
  and `ExportEnvelope`; `Final` is already imported. `app.errors` is deliberately **not** imported
  yet — the raises live in bodies the coder writes, and `F401` is on. The coder adds
  `from app.errors import CharacterNotFoundError, SessionNotFoundError` (both exist in
  `backend/app/errors.py`, 404, no `detail`) along with whatever `sqlalchemy` / `app.db.schema`
  names its selects need.
- Behaviour deliberately left unimplemented: the owner-scoped selects (R5), the exporter's own
  full-row root lookup filtered on both `id` and `user_id` (not the existing getters — `002.context.md`),
  the three memo predicates with "an empty id list contributes no term", and reading messages from
  the **raw** `messages` Table by `session_id` rather than `settled_entries` / `current_zone`.
  All of it is described in the three docstrings and none of it is coded.
- Caller-compile edits (out of Source-files scope): None. No other file was read-modified, no test
  file was touched, and no route exists yet (step 003).
- Gates from `backend/`: `.venv/Scripts/python -m mypy app` → clean (91 files);
  `.venv/Scripts/python -m ruff check .` → clean. pytest not run.

### Step 003 — frozen interface (2026-10-05)

Three Source files, four route declarations, one private helper. Every route body
`raise NotImplementedError`; the router construction, the four route **declarations** and the
`main.py` registration are real, so all four paths exist and `app.main` builds.

`backend/app/routers/transfer.py` (new file):

- `router = APIRouter(tags=["transfer"], dependencies=[Depends(require_user)])` — new. No prefix;
  each handler spells its full literal path, following `routers/search.py`. The guard is
  **router-level**, so a route added later cannot forget it.
- `_attachment(envelope: ExportEnvelope) -> Response` — new (private). The download shape, shared
  by all three routes in this module.
- `export_own_user(current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> Response` — new — `@router.get("/api/export", status_code=200)`
- `export_own_character(character_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> Response` — new — `@router.get("/api/characters/{character_id}/export", status_code=200)`
- `export_own_session(session_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> Response` — new — `@router.get("/api/sessions/{session_id}/export", status_code=200)`

`backend/app/routers/admin_db.py` (changed):

- `export_whole_database(connection: Annotated[Connection, Depends(get_connection)]) -> Response` — new — `@router.get("/export", status_code=200)`, full path `/api/admin/database/export`, inheriting the existing router-level `require_admin` and naming no guard of its own. No path, query or body parameter — like `GET /tables`.
- Module docstring changed (`## Ultra phase` decision 8): "Three routes (`context.md` D9). No query
  parameter, no request body, no rebuild, export or import route anywhere on this router." became a
  **"Four routes"** paragraph that names 030's `GET /export`, says why it lives on this router
  (the inherited admin guard), and **keeps the still-true half of the guard** — "there is still no
  rebuild and no import route anywhere on this router" (031 and `fast/002` own those). A second
  paragraph records the raw-`Response` exception. One earlier sentence was also corrected: "Each
  handler calls exactly one operation — ... `export_database` for the export — and maps its plain
  result onto a model, the export excepted: it answers a raw `Response`".
- No existing route, mapper, import binding or `require_admin` line was otherwise touched.

`backend/app/main.py` (changed):

- `from app.routers.transfer import router as transfer_router` — new, in isort position between
  `stream` and `translation`.
- `app.include_router(transfer_router)` — new, the **last** registration, immediately after
  `app.include_router(search_router)`. Starlette matches in registration order, so every earlier
  router's routes keep matching first (DoD-10).
- **Both** docstring passages that enumerate router order were updated (decision 8; the step text
  mentions only the factory docstring). Module docstring item 5: search's "registered **after every
  other router**" became "after every earlier router" — it is no longer last — and a new final
  sentence adds the transfer router with its three full paths and the 009/011 matching rationale.
  The factory docstring: `app.include_router(transfer_router)` added to the enumeration, and its
  tail now reads "the search router after that (feature `029`), and the transfer router last
  (feature `030`)". No other prose, and no code outside the two lines above, changed.

The attachment response — the shape both routers build locally, recorded here once because it is
the contract and not a behaviour either stub implements:

- status **200** (also on the decorator, `status_code=200`);
- body `encode_envelope(envelope)` (bytes);
- media type `application/json`;
- `Content-Disposition: attachment; filename="<export_filename(envelope)>"`;
- nothing else, and nothing derived from the payload — so the filename carries no character name,
  no session title and no id (DoD-3, US-078 opacity).

Notes on the freeze:

- **Every route returns a raw `Response`, annotated `-> Response`.** That annotation is
  load-bearing, not style: FastAPI skips response-model generation when the return annotation is a
  `Response` subclass, which is what lets a column-agnostic envelope through
  (`003.context.md`; the precedent is `routers/memos.py`'s `delete_own_memo`). A pydantic model
  here would be impossible, and the id boundary is held upstream by step 001's `serialize_row`.
- **Path ids are `SnowflakeIn`, verified end to end.** The generated OpenAPI declares
  `character_id` / `session_id` as `in: path`, `type: integer`, with a `422` response, so a
  non-numeric path id is refused by validation before the handler — and therefore before the
  service — runs (DoD-9). `/api/export` has no parameter and no `422`.
- **`_attachment` is the one private helper frozen, and only in `transfer.py`.** Three routes in
  that module answer the identical shape, so a shared seam is the honest reading of "each router
  builds it locally". `admin_db.py` has a single export route and gets **no** helper — its body
  builds the response inline, and its docstring states the shape. Neither module imports the other.
- **Body-only imports were deliberately withheld** (`F401` is on, same discipline as step 002).
  `transfer.py` imports only what its signatures need: `Annotated`, `APIRouter`, `Depends`,
  `Response`, `Connection`, `get_connection`, `CurrentUser`, `require_user`, `SnowflakeIn` and
  `ExportEnvelope`. The coder adds `encode_envelope`, `export_filename`, `export_user`,
  `export_character` and `export_session` from `app.services.transfer`. `admin_db.py` gained only
  `Response` on its existing `fastapi` import line; the coder adds
  `from app.services.transfer import encode_envelope, export_database, export_filename`.
- **`app.errors` is imported by neither router.** No error is translated in HTTP: the service
  raises `CharacterNotFoundError` / `SessionNotFoundError` (404, R5 — no 403 for a foreign row) and
  the single `DomainError` handler in `app.main` renders them (DoD-7). `require_user` raises the
  401 and `require_admin` the 403 (DoD-2, DoD-8).
- **Handler names** follow the house pattern (`read_drift_report`, `list_own_memos`):
  `export_own_user` / `export_own_character` / `export_own_session` and `export_whole_database`.
  They are the frozen names a monkeypatch or route-table test binds to.
- Caller-compile edits (out of Source-files scope): None. No signature changed, so no call site
  needed adapting; no test file was touched.
- **For the test-coder** (`## Ultra phase` decisions 1 and 2, unchanged by this freeze): the three
  transfer paths go into `tests/test_configuration_router.py`'s `LATER_FEATURE_ROUTES` (not the
  admin-db one), and `tests/test_admin_db_router.py` needs `("GET", f"{PREFIX}/export")` in
  `EXPECTED_OPERATIONS` plus the `/export`-has-no-path-parameter branch in
  `test_router_declares_no_query_parameter_and_no_non_table_key__DoD3`. Nothing asserts either
  `main.py` docstring.
- Gates from `backend/`: `.venv/Scripts/python -m mypy app` → clean (92 files);
  `.venv/Scripts/python -m ruff check .` → clean. pytest not run. App-build probe (throwaway
  `RPHELPER_DATA_DIR` / `RPHELPER_DB_FILENAME` / `RPHELPER_LOG_FILE_PATH`): `app.main` imports,
  54 OpenAPI paths, and all four export paths plus `/api/characters/{character_id}`,
  `/api/sessions/{session_id}` and `/api/admin/database/tables` are present.

### Step 004 — frozen interface (2026-10-05)

One Source file, `frontend/src/shared/api.ts` (changed), **appended to only** — the diff is 38
added lines and 0 removed. Bodies `throw new Error("not implemented")`.

- `frontend/src/shared/api.ts` — `export type DownloadResult = { filename: string; size: number }` — new
- `frontend/src/shared/api.ts` — `export function filenameFromContentDisposition(header: string | null): string` — new (pure)
- `frontend/src/shared/api.ts` — `export async function apiDownload(path: string, signal?: AbortSignal): Promise<DownloadResult>` — new
- Caller-compile edits (out of Source-files scope): None. Nothing imports the three new names
  yet (steps 005 and 006 are their only callers), and no existing signature changed.

Notes on the freeze:

- **No existing export was touched, at all.** `documentNavigation`, `HttpMethod`,
  `decodeErrorResponse`, `mapFetchRejection`, `apiRequest`, `apiGet`, `apiPost`, `apiPatch`,
  `apiPut`, `apiDelete` and the two private helpers (`isPlainObject`, `decodeEnvelope`,
  `malformed`) are byte-identical; `shared/apiError.ts` and `shared/sse.ts` were not opened for
  edit. Per `## Ultra phase` decision 7 the decode needed no extraction — it is already public —
  so DoD-9 holds by construction, and `004.context.md`'s "refactor the decode into a private
  helper if needed" is moot.
- **`filenameFromContentDisposition` is exported, for two reasons.** The step names it as its own
  interface item and it is pure, so the test-coder may bind it directly rather than only through
  `apiDownload`'s resolved `filename` (DoD-3 is satisfiable either way). And mechanically it
  *must* be: `noUnusedLocals` is on and `apiDownload`'s stub body calls nothing, so an
  unexported reader would not compile.
- **The fallback `rphelper-export.json` is documented in the jsdoc, not frozen as a constant.**
  An unused non-exported constant would trip `noUnusedLocals`, and an exported one is surface the
  step did not ask for. The literal comes from the spec (DoD-3); the coder may introduce a
  private constant for it.
- **`DownloadResult` is the importable result name for steps 005 and 006** — a plain object type
  in the module's house style (`HttpMethod`, `CurrentUser`, `SseOutcome`), two fields and no
  more. `size` is the `Blob`'s `size`, a byte count, never a character count; `filename` is a
  name. The type is the opacity boundary: there is deliberately no field through which body
  content could reach a caller.
- **`path` is `string`, not a union of the four export routes.** `apiRequest`'s `/api/` prefix
  check governs `apiRequest` only, and nothing in the plan pins whether `apiDownload` enforces
  the prefix — the choice is left to the coder, and no test binds to it.
- **`signal` is optional**, matching `apiGet` / `apiDelete`: step 005 passes one, step 006 calls
  `apiDownload(path)` with none.
- **Each stub body reads its parameters once via `void x;` before throwing**, with a
  `// stub: delete with the body` comment — `noUnusedParameters` is on and the frozen parameter
  names are part of the record. Those lines go away with the real bodies.
- Behaviour deliberately left unimplemented: the `GET` with `credentials: "same-origin"`, the
  `Blob` read, the object URL / temporary anchor / revoke dance, the `Content-Disposition` parse
  and its fallback, the `decodeErrorResponse` and `mapFetchRejection` calls, and the unwrapped
  abort. All of it is described in the two jsdocs and none of it is coded.
- **For the test-coder:** the three names above are the whole new surface of
  `frontend/tests/shared/apiDownload.test.ts`; `ApiError` / `isApiError` /
  `CLIENT_MALFORMED_ERROR` / `CLIENT_TRANSPORT_FAILED` come from `shared/apiError`, and the 401
  seam is the pre-existing `documentNavigation` export of `shared/api`. jsdom has neither
  `URL.createObjectURL` nor `URL.revokeObjectURL` (`004.context.md`), so both must be stubbed.
- Gate from `frontend/`: `npm run typecheck` → clean (both projects). `npm test` not run, no
  build run.

### Step 005 — frozen interface (2026-10-05)

Two Source files, both changed. Three observable fields, one type alias, two free functions, and
the page's action-group structure. Function bodies `throw new Error("not implemented")`.

**The three new `DatabasePageState` field names (for the two `ALLOWED_FIELDS` lists, `## Ultra
phase` decision 3): `exportStatus`, `exportSizeBytes`, `exportErrorMessage`.** Both lists are
alphabetical, so each becomes
`["applyingTable", "errorMessage", "exportErrorMessage", "exportSizeBytes", "exportStatus", "rows", "status"]`.

`frontend/src/admin/databasePageState.ts` (changed):

- `export type DatabaseExportStatus = "idle" | "exporting"` — new (declared right after
  `DatabaseLoadStatus`, the same house shape)
- `DatabasePageState.exportStatus: DatabaseExportStatus = "idle"` — new field
- `DatabasePageState.exportSizeBytes: number | null = null` — new field
- `DatabasePageState.exportErrorMessage: string | null = null` — new field
- `export async function exportDatabase(state: DatabasePageState, signal?: AbortSignal): Promise<void>` — new
- `export function formatByteSize(bytes: number): string` — new (pure)
- Caller-compile edits (out of Source-files scope): None. No existing field, signature, docstring
  or body was touched; the class's four existing fields and the module's nine existing exports are
  byte-identical, and `makeAutoObservable(this, {}, { autoBind: true })` is unchanged, so the three
  new fields are observable by construction.

`frontend/src/admin/DatabasePage.tsx` (changed):

- No exported signature changed. `DatabasePageProps`, `DatabasePage` and `DatabaseRoute` are as
  they were.
- `const startExport = (): void => { throw new Error("not implemented"); }` — new, inside the
  component, wired to the Export button's `onClick`. **Not** part of the public freeze (a local),
  but it is the seam: the coder replaces the throw with
  `void exportDatabase(state, currentSignal()).catch(ignoreRejection);` and nothing else.

Notes on the freeze:

- **Field names.** `exportSizeBytes` spells its unit on purpose — step 004's `DownloadResult.size`
  is a `Blob`'s byte count, never a character count, and the page's one permitted report is a size.
  `exportErrorMessage` is a second, independent message field beside the drift report's
  `errorMessage` (interface intent: "one failure never overwrites the other's message"), so the two
  inline Alerts are independent and a drift failure is untouched by an export failure (DoD-6).
- **`DatabaseExportStatus` is exported** rather than inlined as a union on the field: it mirrors
  `DatabaseLoadStatus` and `TableStatus`, and the module's style is one named closed union per
  status. It is the fourth status alias in the file and adds no behaviour.
- **The class stays a pure data contract.** Three field declarations with initial values, no
  method, no computed getter, no change to the constructor — `DatabasePageState.prototype` still
  carries only `constructor` (DoD-10).
- **What is real in the page, exactly:** the page-level `Group`
  (`justify="space-between" align="center" mb="md" wrap="nowrap"`) holding the `Title order={2}`
  "Database" and a nested action `Group gap="sm" wrap="nowrap"`; inside it the one
  `Button variant="default"` labelled **Export**, with
  `leftSection={<IconDownload size={ICON_SIZE} stroke={ICON_STROKE} />}` and
  `loading={state.exportStatus === "exporting"}`; a second inline red `Alert` rendered on
  `state.exportErrorMessage !== null`, placed **after** the drift Alert and above the table/Loader
  branch; and the size line, `<Text size="sm" c="dimmed" mb="md">` rendered on
  `state.exportSizeBytes !== null` with the content
  `` `Export downloaded — ${formatByteSize(state.exportSizeBytes)}` ``. The Export button is
  outside the drift `status`/`rows` branch and carries no `disabled`, so it renders and stays
  enabled in every report state (DoD-7).
- **What is left for the coder:** the click handler's body (the only change the page needs) and
  both function bodies. Nothing in the page calls `exportDatabase` yet and the page does **not**
  import it — `noUnusedLocals` would reject an unused import, and the step's rule is structure
  only.
- **`formatByteSize` is called at its real call site**, so the size line is already bound to the
  frozen formatter (DoD-1). Harmless today: nothing sets `exportSizeBytes`, so the line never
  renders from the page's own flow; a test that sets the field by hand will hit the stub's throw,
  which is the intended red.
- **`ICON_SIZE = 18` / `ICON_STROKE = 1.5`** were added as module constants, matching
  `CharacterScreen.tsx`'s page-level action buttons (`IconButton`'s `ICON_SIZES.main`). The
  feature context's `size={16} stroke={1.5}` is the **menu-item** metric and does not apply to a
  page-level `Button`. Both constants are used, so `noUnusedLocals` is satisfied.
- **`noUnusedLocals` / `noUnusedParameters` discipline:** both function stubs read every parameter
  once via `void x; // stub: delete with the body` (step 004's idiom) before throwing; `startExport`
  takes no parameter and is used by `onClick`; every new import (`Button`, `Group`, `Text`,
  `IconDownload`, `formatByteSize`) has a real use in the JSX.
- **Opacity by construction (DoD-2, DoD-3, DoD-4).** The page's whole export surface is the one
  `Button`, the one `Text` size line and the one `Alert`. No viewer, no preview, no details
  affordance, no tooltip, no text input, no filter, no table-name or row-count render, and nothing
  reads the response body — `DownloadResult` exposes only `filename` and `size`, and the page uses
  only `size`.
- **Notifications are not imported.** Neither file imports `@mantine/notifications` or the shared
  notify helper, and the coder must not add either: admin export failures are inline only
  (DoD-5, DoD-6, `005.context.md`).
- **No path constant was frozen.** The route literal `/api/admin/database/export` lives in
  `exportDatabase`'s body, which does not exist yet; an unexported constant would trip
  `noUnusedLocals` and an exported one is surface the step did not ask for (step 004 took the same
  stance on its fallback filename). The coder may add a private constant beside `DRIFT_REPORT_PATH`.
- **No import of `apiDownload` yet**, for the same reason; the coder adds it to the existing
  `from "../shared/api"` line (`apiGet`, `apiPost` are already there) and uses the step-004 frozen
  `apiDownload(path, signal?) : Promise<DownloadResult>`.
- **No stylesheet was touched** and no `.css` file was created; the layout is Mantine props only.
- **For the test-coder:** the bindable new surface is `DatabaseExportStatus`, the three field
  names above, `exportDatabase` and `formatByteSize` from `./databasePageState`; the page's
  accessible control name is exactly `Export` and the size line's wording comes from the step's
  DoD, not from the stub. `## Ultra phase` decision 3 still applies to the two delivered files —
  narrow the out-of-scope regex to `import` / `rebuild` / `re-index` and replace the
  "no control outside the report table" clause; the action group that now exists holds **only**
  the Export button.
- Gate from `frontend/`: `npm run typecheck` → clean (both projects). `npm test` not run, no build
  run.

### Step 006 — frozen interface (2026-10-05)

Four Source files: one new module of free functions (no MobX class) and three delivered
components that gain a control each. Function bodies `throw new Error("not implemented")`.

**`SessionsSection.tsx`'s real path is confirmed as `frontend/src/app/SessionsSection.tsx`** —
011 placed it where `006.context.md` says, so no path correction is needed.

`frontend/src/app/exportDownloads.ts` (new):

- `export function ownDataExportPath(): string` — new (pure; returns the literal `/api/export`)
- `export function characterExportPath(characterId: string): string` — new (pure)
- `export function sessionExportPath(sessionId: string): string` — new (pure)
- `export async function runExport(path: string): Promise<void>` — new (the one shared effect)
- Caller-compile edits (out of Source-files scope): None. The module is new, nothing imported it
  before, and none of the three components imports it yet.

`frontend/src/app/UserMenu.tsx` (changed):

- No exported signature changed. `UserMenuProps` and `UserMenu` are as they were.
- Real: a `Menu.Item` labelled exactly **`Export my data`** with
  `leftSection={<IconDownload size={ITEM_ICON_SIZE} stroke={ITEM_ICON_STROKE} />}`
  (16 / 1.5, the file's existing constants), **unconditional** — every role — placed after the
  admin-only "Admin area" item and **above "Log out"**. `IconDownload` added to the existing
  `@tabler/icons-react` import.
- `const onExportMyData = (): void => { throw new Error("not implemented"); }` — a local seam
  wired to that item's `onClick`. **Not** part of the public freeze.

`frontend/src/app/CharacterScreen.tsx` (changed):

- No exported signature changed. `CharacterScreenProps` and `CharacterScreen` are as they were.
- Real: inside the existing action `Group` at `:282-314`, directly after the Archive/Restore
  ternary, a `Button variant="default"` labelled exactly **`Export`** with
  `leftSection={<IconDownload size={ICON_SIZE} stroke={ICON_STROKE} />}` (18 / 1.5, the file's
  constants) and `loading={exporting}`.
- `const [exporting, setExporting] = useState(false)` — component-local in-flight flag, declared
  beside `submitting` (before every early return). No field was added to `CharacterScreenState`.
- `const onExport = (): void => { void setExporting; throw new Error("not implemented"); }` — the
  local seam wired to the button's `onClick`. **Not** part of the public freeze.

`frontend/src/app/SessionsSection.tsx` (changed):

- No exported signature changed. `SessionsSectionProps` and `SessionsSection` are as they were.
- Real: inside each row's `IconDots` dropdown (accessible name `Actions for <label>`, where
  `label = formatSessionStart(session.created_at)`), **after** the Archive/Restore ternary and so
  **present in both states**, a `Menu.Item` labelled exactly **`Export`** with
  `leftSection={<IconDownload size={MENU_ICON_SIZE} stroke={ICON_STROKE} />}` (16 / 1.5).
- Its `onClick` is an inline arrow that throws — the per-row seam, with `session.id` in scope.
  **Not** part of the public freeze.

Notes on the freeze:

- **The render condition for the character Export button is "inside the Archive/Restore `Group`",
  and nothing more.** Per `## Ultra phase` decision 8 that `Group` holds **no Save button** (018
  step 009 removed it) and is *unconditional* within the existing-mode return, which is reached
  only after four early returns: `isNewCharacter(state)` (the draft page, `:159`, renders no
  `Group` at all), `status === "loading"`, `status === "not-found"` and `status === "failed"`.
  Placing the button in that `Group` therefore satisfies "exactly the same condition as
  Archive/Restore" **with no new predicate**, and DoD-5 (the draft page renders no Export button)
  holds by construction. `006.context.md`'s "the Save `Button` and an Archive/Restore `Button`"
  is the stale description decision 8 corrects.
- **`ownDataExportPath` is a function, not a constant**, so all three builders are callable in the
  same shape and the test-coder binds to one surface. It takes no parameter: `/api/export` is
  scoped to the authenticated session server-side.
- **Ids are `string` and are never parsed.** No parameter or field in the step is annotated
  `number`, no `parseInt` appears, and the two id-bearing builders interpolate their argument
  verbatim — so a 19-digit id past `Number.MAX_SAFE_INTEGER` survives (DoD-1) and
  `frontend/tests/ids-are-strings.test.ts` stays green.
- **`runExport` returns `Promise<void>`, not a success boolean.** The step's prose gives it no
  result ("resolves on success and on handled failure, and never rethrows"), and opacity forbids
  reporting anything about the body in the `app` entry — there is no size line here, unlike step
  005's admin page. Call sites are `void runExport(...)`, or `await` where the character screen
  must clear `exporting`.
- **`exportDownloads.ts` imports neither `apiDownload` nor `notifyFailure` yet**, and imports
  `@mantine/notifications` **never**. `noUnusedLocals` would reject an unused import against a
  throwing body (step 005 took the same stance). The coder adds
  `import { apiDownload } from "../shared/api";` and
  `import { notifyFailure } from "../shared/notifyFailure";` — and must not add a third importer
  of `@mantine/notifications`, or `frontend/tests/conventions.test.ts:132-138` fails.
- **The abort predicate is left to the coder** as a private module helper, matching the five
  existing copies of `function isAbortRejection(error: unknown): boolean { return error instanceof
  Error && error.name === "AbortError"; }` (`admin/databasePageState.ts:101` and friends). An
  unused private helper would trip `noUnusedLocals`, so none is declared here.
- **Each component's click is a seam that throws, never a no-op.** A silent handler would let
  DoD-8's "no confirm dialog appears" clause pass against the skeleton; a throw cannot. This
  mirrors step 005's `startExport`.
- **No stylesheet was touched** and no `.css` file created — Mantine props only, so
  `frontend/tests/stylesheets.test.ts` is unaffected. `shared/api.ts` (step 004) and the admin
  entry (step 005) were not opened for edit.
- Behaviour deliberately left unimplemented: the three path strings themselves; `runExport`'s
  `await apiDownload(path)`, its abort test and its single `notifyFailure` call; and all three
  click handlers' real bodies (which id goes to which builder, and the character screen's
  `setExporting` pair). Nothing calls `runExport` anywhere yet.
- **For the test-coder:** the bindable new surface is the four names above from
  `./exportDownloads` (`frontend/tests/app/exportDownloads.test.ts`). The three accessible control
  names are exactly `Export my data` (menu item), `Export` (the character screen's button) and
  `Export` (the row menu item, reached through the `Actions for <label>` trigger, where the label
  is the start-time text from `formatSessionStart(session.created_at)` — never the id). The
  character row-menu dropdown now holds **two** items per row (Export plus Archive xor Restore),
  the first time it has held more than one. `ApiError` comes from `shared/apiError`; jsdom stubs
  for `URL.createObjectURL` / `revokeObjectURL` are needed per file (`004.context.md`), and
  `notifyFailure` is spyable at `src/shared/notifyFailure.ts`.
- Gate from `frontend/`: `npm run typecheck` → clean (both projects). `npm test` not run, no build
  run.

## Tests

### Step 001 — tests (2026-10-05)

- `backend/tests/test_transfer_core.py` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-6, DoD-7,
  DoD-8, DoD-9, DoD-10, DoD-11 — 22 tests over the whole-database envelope: header keys and
  values, the payload's computed `sorted_tables` order minus the exclusions, the two excluded
  tables with rows present, no non-registry / FTS / vec key, every seeded row and every declared
  column, the three arms of the id rule plus nulls, booleans / `memos.scope` / timestamps /
  non-id integers / the `users.role` enum, credentials carried as stored with the named
  environment variable's sentinel absent from the encoded bytes, ascending primary-key order,
  the UTF-8 JSON round trip including non-ASCII, and the filename's shape and opacity.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 [manual/live, no test]
- Honours `## Ultra phase` decisions 4 (order computed from `schema.metadata.sorted_tables`),
  5 (the enum arm covered on `users.role` as well as `memos.scope`'s `str` path), 6 (the real
  four 024 tables, no `session_fts`) and 8 (`model_server_id` on both `characters` and
  `sessions`, `messages.related_to` via the FK arm, `models.embedding_dim` / `memos.sort_key`
  as plain numbers).
- **Red-gate round 1 repair (2026-10-05, fault TEST, finding 1).** The fixture died at setup on
  `ck_characters_model_both_or_neither`: `_insert_character` and `_insert_session` forwarded
  `model_server_id` without its companion `model_name`, and feature 017's skeleton froze that pair
  as both-NULL-or-both-non-NULL on **both** tables. Both helpers now write the pair together —
  `model_name=MODEL_NAME if model_server_id is not None else None` — against a new `MODEL_NAME`
  constant (also reused by `_insert_model`), with the constraint named in a `#:` comment and at
  each helper. `CHAR_A1` and `SESSION_A1` keep the non-null pair; `CHAR_A2`, `CHAR_B1`,
  `SESSION_A2` and `SESSION_B1` keep **both** columns NULL, so DoD-6's "a null reference stays
  `null`" still has its subject on `characters` (asserted on `CHAR_A2`) as well as on `sessions`.
  No row set, id, archived flag, buried-message construction or assertion changed.

### Step 002 — tests (2026-10-05)

- `backend/tests/test_transfer_selections.py` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-6,
  DoD-7, DoD-8, DoD-9, DoD-10, DoD-11, DoD-12, DoD-13, DoD-14 — 20 test functions (22 collected
  cases; the two not-found tests are parametrized over the foreign and the unknown id) over the three
  owner-scoped envelopes: each payload's table set plus its **computed** key order, the caller's
  `users` row minus the three account-state columns, memos at all four scopes, owner isolation
  against a second seeded owner (no id of theirs appears as any serialized value), the
  `user_id`-column classification guard, the character's archived setups and sessions with all
  three message states, the character memo predicate against a sibling character / setup /
  session, the character export's absent keys, both not-found arms for character and session,
  an archived root still exporting, the session's full message set with every `related_to`
  resolving inside the payload, the session memo predicate against a sibling session under the
  same character, and the id rule in all three exports.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 [manual/live, no test]
- Honours `## Ultra phase` decision 4: DoD-1's and DoD-12's enumerations are asserted as **sets**,
  and every key order is computed from `schema.metadata.sorted_tables` — no sequence is
  hard-coded.
- Both files are self-contained: a file-local `engine` fixture over the existing `db_settings` /
  `db_engine`, file-local raw-insert helpers, two users, ids above 2**60. `conftest.py` and
  `llm_fakes.py` were not touched, and no delivered test file was amended.
- **Red-gate round 1 repair (2026-10-05, fault TEST, finding 1).** Same cause and same fix as
  step 001's, applied to this file's `_insert_character` and `_insert_session`: the
  `model_server_id` / `model_name` pair is now written together against a file-local
  `MODEL_NAME`, honouring `ck_characters_model_both_or_neither` and
  `ck_sessions_model_both_or_neither`. `CHAR_A1` and `SESSION_A1` keep the non-null pair;
  `CHAR_A2`, `CHAR_B1`, `SESSION_A2`, `SESSION_A3` and `SESSION_B1` keep **both** columns NULL,
  which is what the DoD-14 id-rule helper's null arm reads on the character and session
  envelopes. No row set, id, archived flag, memo seeding or assertion changed.
- **`settle()` seeding path, re-checked (finding 1's follow-up).** The verifier could not reach it
  because the fixture died first. It is safe: the delivered `backend/tests/test_settle_service.py`
  seeds exactly the same way these two files do — `db_engine` plus `schema.metadata.create_all`
  and nothing else, so no FTS5 or `vec0` table exists and no model is designated — calls
  `settle(connection, user_id, session_id)` on a plain `engine.connect()` connection, and its
  whole suite passes. Its docstring records 024 step 005's DoD-9 explicitly: with no model
  designated "every settle and re-open still succeeds (the record-keeping posture degrades, it
  does not fail — `context.md` D8)". The degraded `session_vec` refresh through
  `app.services.session_index` is a permitted, non-raising path. Conclusion: no off-contract
  dependency remains; both fixtures' three-row-zone settle should seed the buried rows as
  `002.context.md` "Seeding buried messages" directs.

### Step 003 — tests (2026-10-05)

- `backend/tests/test_transfer_router.py` — covers DoD-3, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8,
  DoD-9, DoD-10 — 16 test functions (26 collected cases; DoD-3 and DoD-9's body-id test are
  parametrized over the three routes, DoD-7's two over the foreign and the unknown id, DoD-8 over
  the three paths, and DoD-9's 422 and declaration tests over the two parameterised routes) over
  the three roleplayer routes: the opaque `attachment; filename="rphelper-<granularity>-<timestamp>.json"`
  header for each granularity with the seeded character name, setup name, session memo body and
  every seeded id absent from it; the user export's single `users` row without `password_hash` (key
  **and** stored value) plus the caller's memos and the second owner's own export; the character
  export's root row and its character/setup/session memos only; the session export's root row and
  its session memo only, from both sides of the sibling pair; 404 `character_not_found` /
  `session_not_found` for a foreign **and** an unknown id with an explicit `!= 403` and an
  identical-body comparison; 401 `not_authenticated` on all three without a cookie; every id column
  of every exported row a decimal string, the native 422 for a non-numeric path id carrying neither
  not-found code, and the OpenAPI declaration (one integer path parameter plus a `422`) that puts
  the refusal before the service; and the DoD-10 smoke reads of `GET /api/characters/{id}` and
  `GET /api/sessions/{id}`.
- `backend/tests/test_admin_db_export.py` — covers DoD-1, DoD-2, DoD-3, DoD-9, DoD-10 — 9 tests
  over `GET /api/admin/database/export`: 200 / `application/json` / `format` `"rphelper-export"` /
  `granularity` `"database"`, the unscoped read carrying the roleplayer's character and session, the
  inherited `require_admin` answering 403 `insufficient_role` to a roleplayer and 401
  `not_authenticated` to an anonymous caller, a refusal leaking neither envelope nor attachment, the
  opaque `rphelper-database-<timestamp>.json` filename, every id in the body a decimal string, the
  route declaring no parameter, and the DoD-10 smoke read of `GET /api/admin/database/tables`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 [manual/live, no test], DoD-12 [manual/live, no test]
- Both new files are self-contained, following `tests/test_characters_router.py` /
  `tests/test_memos_router.py`: the real factory's application pinned to the per-test `tmp_path`
  database through `dependency_overrides[get_settings]`, the autouse no-op of
  `app.main.configure_logging`, file-local `_insert_user` / `_login_token` / `_as` / `_anonymous` /
  `_assert_envelope` helpers and raw inserts over the `schema.*` Table objects (no memo route, so no
  embedding provider is involved). Ids are above 2**60. `conftest.py` was not touched.
- **Note on DoD-3's wording:** `db/schema.py`'s `sessions` table carries no `title` column, so the
  clause's "distinctive title" is seeded as the session-scope memo body (plus the session's own id)
  and asserted absent from the header. Both files record this in their module docstring.
- Amendment (`## Ultra phase` decision 1) — `backend/tests/test_configuration_router.py`: the three
  transfer routes `("/api/export","GET")`, `("/api/characters/{character_id}/export","GET")` and
  `("/api/sessions/{session_id}/export","GET")` added to `LATER_FEATURE_ROUTES`, and its `#:`
  comment extended the way 023 and 029 did, citing 030 step 003 and recording why
  `("/api/admin/database/export","GET")` is deliberately **not** in the set. No test body changed
  and nothing else in the file changed.
- Amendment (`## Ultra phase` decision 2) — `backend/tests/test_admin_db_router.py`, two sites:
  `EXPECTED_OPERATIONS` gains `("GET", f"{PREFIX}/export")` with an `S030_003_DoD10` comment, and
  `test_router_declares_only_the_three_routes__DoD3` is renamed
  `test_router_declares_exactly_the_expected_routes__DoD3` with its docstring reworded off "only
  the three routes" and off "no route that could return a count exists on this router's surface";
  `test_router_declares_no_query_parameter_and_no_non_table_key__DoD3`'s branch is widened to
  `path.endswith(("/tables", "/export"))` so `/export` joins `/tables`' no-path-parameter arm, with
  the same note in its docstring. Every `__DoD<n>` tag is kept and no assertion was dropped.
- **Red-gate round 1 repair (2026-10-05, fault TEST, finding 2) — two more delivered guards in
  `backend/tests/test_admin_db_router.py`, missed by decision 2.** Both asserted the absence of
  exactly the route 030 ships. Both are **narrowed, not disarmed**, each carrying an
  `S030_003_DoD1` note beside the change and keeping its `__DoD14` tag:
  - `test_route_surface_has_no_rebuild_export_import_or_vector_route__DoD14` renamed
    `test_route_surface_has_no_rebuild_import_or_vector_route__DoD14`. `FORBIDDEN_SURFACE` drops
    `"export"` and keeps `("rebuild", "import", "vector", "vec0")`, still rejected on **every**
    operation; a new `PERMITTED_EXPORT_OPERATION = ("GET", f"{PREFIX}/export")` is the sole
    exemption, and the test still asserts `"export" not in path` for every other operation. The
    `set(operations) == EXPECTED_OPERATIONS` pin is unchanged, so no unexpected route can slip in.
  - `test_out_of_scope_routes_do_not_exist__DoD14`: only `("GET", f"{PREFIX}/export")` leaves the
    parametrization. `POST .../rebuild`, `POST .../vector-index/rebuild`,
    `POST .../tables/models/rebuild`, `POST .../export`, `POST .../import` and
    `GET .../vector-index` all stay armed — 031 owns Import, `fast/002` owns Rebuild, and 030
    ships a GET download and no POST verb. Title and docstring reworded off "export".
  - The module docstring gains an "Amended by feature 030, step 003" paragraph covering all four
    sites. `test_route_surface_documents_nothing_about_a_vector_index__DoD14` and
    `test_router_issues_no_sql_opens_no_transaction_and_translates_no_error__DoD13` were **not**
    touched; the latter's single-`ast.Raise` failure is the accepted true-red from the step-003
    skeleton's stub and must go green on its own when the body is filled.

### Step 004 — tests (2026-10-05)

- `frontend/tests/shared/apiDownload.test.ts` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-6,
  DoD-7, DoD-8, DoD-9 — 13 `it` blocks, 26 collected cases (DoD-3's pure reader is parametrized
  over three quoted headers and four fallback headers, DoD-5 over four statuses, DoD-7 over four
  non-envelope bodies): one GET of the given path with `credentials: "same-origin"` and a `size`
  equal to the body's **byte** length (asserted different from its character length, via a
  multi-byte fixture); the object URL created from the body (its byte size and its text both
  checked), a single anchor click carrying that URL as `href` and the header's filename as
  `download`, and the URL revoked afterwards with the create/click/revoke order pinned; the quoted
  `Content-Disposition` filename and the `rphelper-export.json` fallback, through both
  `apiDownload` and the exported pure `filenameFromContentDisposition`; no anchor left in the
  document; a non-2xx envelope rejecting with its code, message and real status and **no** object
  URL created; a 401 navigating through the `documentNavigation` seam and then rejecting with
  status 401; `client_malformed_error` with the real status for four non-envelope bodies and
  `client_transport_failed` with status 0 for a `fetch` rejection; an already-aborted and a
  mid-flight abort both rejecting with the signal's own reason, not an `ApiError`; and the DoD-9
  regression of `apiGet` / `apiPost` on a 2xx body and on an error envelope.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 [manual/live, no test]
- Harness: `fetch` stubbed per test with `vi.stubGlobal`; `URL.createObjectURL` /
  `URL.revokeObjectURL` installed per test and removed afterwards (jsdom has neither); the anchor
  click observed through a spy on `HTMLAnchorElement.prototype.click`, which also keeps jsdom from
  navigating. No new setup file (`build-config.test.ts` pins `setupFiles`).
- **DoD-9's two clauses should be green against the skeleton** (`## Ultra phase` decision 7 and the
  skeleton's append-only record); every other clause in the file is expected red.
- The revoke is awaited through `vi.waitFor`, so a deferred revoke still satisfies "afterwards"
  while the create → click → revoke ordering stays asserted.

### Step 005 — tests (2026-10-05)

- `frontend/tests/admin/databasePageExport.test.ts` — covers DoD-1, DoD-8, DoD-9, DoD-10 — 13 `it`
  blocks, 22 collected cases (DoD-9 is parametrized in three groups of four): `exportDatabase`
  downloading `/api/admin/database/export` and passing its signal straight through; the size stored
  on success with no export error and the status back to `idle`; the failure's message stored with
  no size; both the previous size **and** the previous export error cleared at the start of a new
  export (observed mid-flight through a deferred download, with the status `exporting`); nothing
  written at all when the signal is already aborted; the drift report's own `errorMessage`
  untouched in every arm; `formatByteSize` for `0 B` / `1 B` / `512 B` / `1023 B`, `1.0 KB` /
  `1.5 KB` / `12.3 KB` / `1023.4 KB`, `1.0 MB` / `4.0 MB` / `12.5 MB` / `1024.0 MB`; and the data
  contract — the prototype carrying only `constructor`, each of the three new fields observable,
  non-computed and never a function, and a fresh store `idle` with both nullable fields null.
  `apiDownload` is replaced at module level (every other `shared/api` export passed through), so
  the effect's contract is observed without a network call.
- `frontend/tests/admin/DatabasePage.export.test.tsx` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5,
  DoD-6, DoD-7 — 13 `it` blocks, 15 collected cases (DoD-7 parametrized over the in-sync, drifted
  and missing-row reports): a click on Export issuing one GET of the export route and the page then
  showing the formatted size, with no size line before any export; the opacity clause (below); the
  only export-named control being the Export button and no view/open/preview/browse/details
  affordance, before **and** after an export; no textbox, searchbox, combobox, `input` or
  `textarea` on the page, before **and** after; a success raising nothing in the notifications
  outlet and opening no `Alert`; a failure rendering its message in an inline red `Alert`, raising
  no notification, showing no size line and leaving the drift rows and the drift `errorMessage` as
  they were; a second failure case proving the two messages are independent (a failed drift load
  plus a failed export renders both, each field holding its own); and the Export button's
  accessible name being exactly `Export`, present and enabled in all three drift states and even
  when the drift load failed.
- **How DoD-2 is kept non-vacuous:** the export response is a 2048-byte envelope whose payload
  carries a username, a character name, memo text, three snowflake ids and the table names
  `users` / `characters` / `memos`, while the drift report deliberately lists a **disjoint** set
  of tables (`llm_servers`, `models`, `translations`) — so a rendered "characters" could only come
  from the export. A separate clause asserts that the fixture really contains every sentinel and
  really is 2048 bytes; the opacity clause then asserts the export fetch happened **and** that the
  page shows `2.0 KB` (proof it consumed that very response) before asserting every sentinel
  absent from the readable text and the naming attributes, that no digit-bearing count claim
  appears, and that the table rows name only the three drift tables.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 [manual/live, no test], DoD-12 [manual/live, no test]
- Harness: the page renders inside `AppProviders` + `MemoryRouter`, so `.mantine-Notification-root`
  is observable; `fetch` is stubbed once per file and routed by **exact pathname**, answering
  `GET /api/admin/database/tables` as well as the export route; `URL.createObjectURL` /
  `revokeObjectURL` and `HTMLAnchorElement.prototype.click` are stubbed as in step 004. Readable
  text excludes `style`/`script` contents and includes the naming attributes. No `.css` file was
  created and no stylesheet was touched.
- Expected green against the skeleton: the two "before an export" clauses (DoD-3, DoD-4), the
  "no size line before any export" clause (DoD-1), the DoD-7 presence/enabled clauses, the DoD-2
  fixture self-check, and the whole data-contract block (DoD-10). Everything that clicks Export or
  calls `exportDatabase` / `formatByteSize` is expected red — the click seam and both function
  bodies throw.
- Amendment (`## Ultra phase` decision 3) — `frontend/tests/admin/databasePage.test.tsx`, six
  sites, all tagged `S030_005_DoD<n>` beside the change, every `DoD-10` id kept and no assertion
  dropped: `OUT_OF_SCOPE_CONTROL` narrowed to `/\b(import|rebuild|re-?index)(s|ed|ing)?\b/i` with a
  jsdoc recording that Import (031) and Rebuild (`fast/002`) stay armed and must never be
  permitted; the four clauses sharing that regex (the control sweep, the readable-text sweep, the
  empty-report/failed-load sweep and the page-source literal scan) keep their assertions verbatim
  and only lose "Export" from their titles; the clause "the page has no control outside the report
  table — no header action bar" is **replaced** by "the only control outside the report table is
  the Export action", which asserts `outside.map(controlName).map(squash)` equals exactly
  `["Export"]` — so a stray second control outside the table still fails; and `ALLOWED_FIELDS`
  gains the three new field names, becoming
  `["applyingTable", "errorMessage", "exportErrorMessage", "exportSizeBytes", "exportStatus", "rows", "status"]`.
- Amendment (`## Ultra phase` decision 3) — `frontend/tests/admin/databaseActions.test.tsx`, two
  sites: `OUT_OF_SCOPE_ITEM` narrowed to `/rebuild|import|re-?index/i` for the page-wide control
  sweep, while a new `OUT_OF_SCOPE_ROW_ITEM` keeps the **full** `/rebuild|export|import|re-?index/i`
  and is used by the row-menu clause (no Export item may ever land in a row dropdown); and this
  file's own independent `ALLOWED_FIELDS` copy gains the same three names. Both `DoD-14` /
  `DoD-15` tags kept, nothing dropped.
- `npm run typecheck` was **not** run: no shell tool was available in this run. Both new `.ts`
  files and the `.tsx` file are written against `strict` + `noUnusedLocals` /
  `noUnusedParameters`, but the typecheck gate is unverified here. The red gate later reported it
  **clean** across all of this step's files and both amendments.
- **Repair after red-gate round 1 (Fault TEST, finding 3) — 2026-10-05.** Two clauses in
  `DatabasePage.export.test.tsx` asserted only absences after the Export click, so they passed
  against the bare skeleton: React swallows the throwing click handler, making "nothing appeared"
  indistinguishable from "nothing happened", and they would also pass against an implementation
  that does nothing. The `## Ultra phase` reasoning that "every click seam throws, so an
  absence-shaped clause cannot pass vacuously" holds only for clauses that *also* prove the
  request reached `fetch`. Both now open with a positive anchor, exactly the shape the DoD-2
  opacity clause already used — `expect(exportCalls(mock)).toHaveLength(1)` plus
  `expect(readableText()).toContain(EXPORT_SIZE_TEXT)` — and every pre-existing assertion, title
  and `— DoD-N` tag is unchanged: "after a successful export the only export-related control is
  still the Export button — DoD-3" and "after a successful export the page still offers no search
  or filter input — DoD-4". Their "before an export" twins, `databasePageExport.test.ts` and both
  amendment files were not touched.

### Step 006 — tests (2026-10-05)

- `frontend/tests/app/exportDownloads.test.ts` — covers DoD-1, DoD-2 — 13 `it` blocks, 23
  collected cases (three DoD-1 blocks parametrized over four ids, the abort block over two abort
  shapes): `ownDataExportPath()` returning exactly `/api/export` and declaring no parameter;
  `characterExportPath` / `sessionExportPath` returning `/api/characters/<id>/export` and
  `/api/sessions/<id>/export` for `1`, `9007199254740993` (2^53 + 1), `7250000000000000011` and
  `9999999999999999999`; the id re-extracted from each built path and compared to the argument, so
  any reformatting shows; a standalone 19-digit clause that first proves `String(Number(id))`
  differs from the id and then pins both paths; the three builders answering three distinct
  routes; `runExport` awaiting `apiDownload` once with exactly the path it was given; a success
  resolving `undefined` with `notifyFailure` never called; a failure calling `notifyFailure`
  **exactly once** with the very thrown `ApiError` instance (identity, not shape) and with that
  error's own message, and still resolving rather than rethrowing; a non-`ApiError` thrown value
  notified once as well; and an abort — both a `DOMException` named `AbortError` and an `Error`
  renamed to it — notifying nothing and still resolving.
- `frontend/tests/app/UserMenu.export.test.tsx` — covers DoD-3, DoD-7, DoD-8 — 6 `it` blocks, 8
  collected cases (two blocks parametrized over `roleplayer` / `admin`): the `Export my data`
  menu item present for both roles; choosing it as either role issuing exactly
  `[{ GET, /api/export, no query }]` and **nothing else** (the menu makes no other request); the
  item being a plain menu item with no `href` (so it is not a second document link, which 008's
  delivered DoD-3 clause also forbids); a success raising no notification, showing no
  success-wording and never leaking the downloaded filename into the page; a failure raising
  exactly one notification whose text contains the envelope's message; and one click reaching the
  request with no `dialog` / `alertdialog` anywhere.
- `frontend/tests/app/CharacterScreen.export.test.tsx` — covers DoD-4, DoD-5, DoD-7, DoD-8 — 8
  `it` blocks, 8 collected cases: an active character's `Export` button resolving to the **same**
  `.mantine-Group-root` ancestor as `Archive`, and an archived character's to the same one as
  `Restore` (with `Archive` absent) — the grouping, not merely the presence; a click issuing
  exactly one `GET /api/characters/7250000000000000011/export` and never a second character's
  export path; the archived character exporting through the same route; the draft page at
  `/characters/new` rendering no `Export` button in the main region **or** anywhere in the
  document, no `Archive`/`Restore` either, and sending no request at all; a success raising no
  notification, no success-wording and no filename; a failure (404 `character_not_found`) raising
  exactly one notification carrying the envelope's message; and one click reaching the request
  with no dialog before or after it.
- `frontend/tests/app/SessionsSection.export.test.tsx` — covers DoD-6, DoD-7, DoD-8 — 9 `it`
  blocks, 9 collected cases: an active row's `Actions for <label>` menu holding `Export`
  alongside its `Archive` item; an archived row's holding `Export` alongside `Restore` (with
  `Archive` absent), reached after the `Show archived sessions` switch; choosing `Export` in the
  **first** active row requesting that row's export path and never the second's, the mirror case
  for the second row, and the same for the archived row — three rows with three different ids, so
  a wrong-id implementation fails; the export being a `GET` with an empty query; a success raising
  no notification, no success-wording and no filename; a failure (404 `session_not_found`) raising
  exactly one notification carrying the message; and one click reaching the request with no
  dialog.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓ (all three controls),
  DoD-8 ✓ (all three controls), DoD-9 [manual/live, no test], DoD-10 [manual/live, no test]
- **How notifications are observed, and why two ways.** The three component files render inside
  `AppProviders` and read the real `.mantine-Notification-root` outlet, because DoD-7 is about
  what the *user is shown* ("one notification carrying the error's message") — a spy could not
  show that the message reaches the screen. `exportDownloads.test.ts` instead replaces
  `shared/notifyFailure` with a mock module, because DoD-2 is about the *call* ("exactly once,
  with the thrown `ApiError`", "not at all" on success and on abort), which only a spy can count.
  It also replaces `apiDownload` at module level (every other `shared/api` export passed
  through), the step 005 precedent, so `runExport`'s contract needs no network and no jsdom
  download dance.
- Harness: `fetch` stubbed per file with `vi.stubGlobal` and routed by **exact pathname** (the
  three component files), restored in `afterEach`; `URL.createObjectURL` / `URL.revokeObjectURL`
  installed per test and removed afterwards (jsdom has neither) because `apiDownload` runs for
  real in the component files; the anchor click swallowed by a spy on
  `HTMLAnchorElement.prototype.click`, and `documentNavigation.assign` spied so no 401 path could
  navigate jsdom. Menus are driven with `userEvent.setup({ pointerEventsCheck: 0 })` and
  accessible names. Rows are identified by their `/sessions/<id>` link href, never by the
  start-time label (011's convention); the three session fixtures start in different minutes so
  each `Actions for <label>` trigger name is unique. "Readable text" excludes `style`/`script`
  contents. `src/shared/MarkdownEditor` is replaced by the repo's sanctioned jsdom stub in the
  character-screen file. No `.css` file was created and no stylesheet was touched.
- **"No success text" is a word list, not a substring scan:**
  `/\b(success|succeeded|successfully|downloaded|exported|completed|finished)\b/i`, checked over
  the readable text after a successful export. Ambiguous words (`saved`, `done`, bare `complete`)
  are deliberately excluded so the draft page's "Nothing is saved until you enter a name." and
  similar delivered copy cannot make the clause false for the wrong reason.
- **No delivered file was amended.** The harvest's §6.5 sweep found none of
  `UserMenu.test.tsx`, `CharacterScreen.test.tsx` or `SessionsSection.test.tsx` breaking (none
  enumerates its controls exhaustively), and nothing in them had to be widened.
- Expected green against the skeleton: the two presence clauses that never click — the user
  menu's `Export my data` item for both roles and the item's "no `href`" clause — plus the
  character screen's two grouping clauses and the whole DoD-5 draft-page clause (the draft branch
  renders no `Group` at all), and the session rows' two menu-contents clauses. Everything that
  clicks a control or calls one of the four new functions is expected red: all four bodies and
  all three click seams throw, so the DoD-8 "no confirm dialog" clauses cannot pass vacuously.
- `npm run typecheck` was **not** run: no shell tool was available in this run. The four files are
  written against `strict` + `noUnusedLocals` / `noUnusedParameters` (no unused helper, every
  `it.each` tuple parameter either used or `_`-prefixed), but the typecheck gate is unverified
  here. The red gate later reported it **clean** across all of this step's files.
- **Repair after red-gate round 1 (Fault TEST, finding 4) — 2026-10-05.** The clause "a successful
  export raises no notification and shows no success text — DoD-7" in each of the three component
  files was a pre-check that already passed, a click, and three negative assertions — so it passed
  against the bare skeleton, because React swallows the throwing click handler and "nothing
  appeared" is then indistinguishable from "nothing happened". (The DoD-8 clauses in the same
  files are correctly red precisely because they also assert the request reached `fetch`.) Each
  now carries that same positive anchor before its silence assertions, asserting one `GET` of that
  control's own path with an empty query: `UserMenu.export.test.tsx` —
  `exportRequests(calls)` equals `[{ GET, /api/export, "" }]`;
  `CharacterScreen.export.test.tsx` — `matching(calls, "GET", exportPath(ID_A))` equals that one
  request; `SessionsSection.export.test.tsx` — the same for `exportPath(ROW_A.id)`. Every title,
  `— DoD-N` tag and pre-existing assertion (no notification root, no success wording, the filename
  nowhere on the page) is unchanged; nothing was removed and `exportDownloads.test.ts` and the
  DoD-8 clauses were not touched.

- code: done — steps 001..006 (no re-freeze, no escape valve)
- verify: **PASS (run 2)** — run 1 FAIL: **006 CODE**. Backend **4353 passed / 0 failed / 0
  errored** (mypy clean on 92 files, ruff clean); frontend **4193 passed / 0 failed** across 144
  files (typecheck clean on both projects, build clean, four entries emitted). Both numbers are the
  red gate's full collection, so the 65 `NotImplementedError` reds and the one accepted true-red
  are all cleared with nothing previously green turned red.

### Verify round 1 — step 006, Fault CODE (DoD-2, the abort half)

DoD-2 requires `runExport` to stay **silent** when the download rejects with an abort error. The
delivered private predicate admitted a thrown value only when it was an `instanceof Error` whose
`name` was `AbortError` — but the abort rejection the web platform actually raises, and the one
**this feature's own `apiDownload` throws from its post-body-read abort re-check**, is a
`DOMException`, which is not an `Error` instance in jsdom or in browsers. So the real abort fell
through the guard and reached `notifyFailure`; only the hand-rolled `Error`-with-`name`-reassigned
shape was handled. Not a test-environment artefact: a roleplayer navigating away mid-download
would have been shown an error notification on the way out of the page.

Fixed in `frontend/src/app/exportDownloads.ts` alone, in the private predicate only — the four
frozen signatures and `runExport`'s body were untouched, and no other file in the repository
changed (the verifier confirmed this two ways: a timestamp sweep over `backend/app`,
`backend/tests`, `frontend/src`, `frontend/tests` returns that one path, and `git status
--porcelain` is unchanged from run 1). The predicate now matches on `name` alone,
constructor-independent: a non-null object whose `name` is exactly `AbortError`. Over-admission was
ruled out explicitly — `ApiError` sets `name = "ApiError"`, so every `ApiError` (including
`client_malformed_error` and `client_transport_failed`), every other named `Error`, every object
without a `name` and every non-object value still reaches exactly one `notifyFailure` with the
thrown value.

**Accepted true-red cleared.** `backend/tests/test_admin_db_router.py`'s
`test_router_issues_no_sql_opens_no_transaction_and_translates_no_error__DoD13` — the AST walk
asserting **no `ast.Raise` node anywhere** in `app/routers/admin_db.py` — is green again, confirmed
independently at 0 nodes in that router and 0 in `app/routers/transfer.py`. 007's D13 therefore
still holds with 030's fourth route on the router.

**All five designed guards verified still armed**, narrowed and never disarmed: `FORBIDDEN_SURFACE`
is now `("rebuild","import","vector","vec0")` rejected on every operation, with `export` admitted
on **exactly one** path (`GET /api/admin/database/export`) and still rejected everywhere else;
`LATER_FEATURE_ROUTES` gained the three roleplayer transfer routes and deliberately **not** the
admin-db export route; both frontend out-of-scope regexes still match `import` / `rebuild` /
`re-index`; `OUT_OF_SCOPE_ROW_ITEM` is still the full `/rebuild|export|import|re-?index/i`, so an
Export item in a **row** dropdown would still fail; and the replacement "only control outside the
table" clause pins that set to exactly `["Export"]`.

### Carried forward out of 030's scope

- **The house abort predicate has the same blind spot in five other places.** The narrow
  `error instanceof Error && error.name === "AbortError"` form still lives in
  `frontend/src/admin/databasePageState.ts` and four siblings; those copies are mostly shielded by
  an `signal?.aborted` pre-check that runs first, but they would misclassify a real
  `AbortController` abort. Worth a sweep in a later feature — **not** a defect in any 030 step.
- Step 005's `exportDatabase` returns on a mid-flight abort without restoring `exportStatus` to
  `"idle"`, leaving the button in its loading state. Consistent with DoD-8's "writes nothing when
  aborted" and unobservable in practice (the signal is the page's own unmount controller).
- `_serialize_value`'s terminal `return str(value)` is a JSON-safety catch-all for a column type the
  registry does not currently declare; it would stringify rather than surface a new shape. Worth a
  thought when `schema_version` next moves.
- `characterExportPath` / `sessionExportPath` interpolate through `encodeURIComponent`, while the
  step prose says "verbatim". Byte-identical for every decimal id the app carries; a wording
  mismatch only.
- `test_out_of_scope_routes_do_not_exist__DoD14` still arms `GET .../vector-index`, so `fast/002`
  will have to **narrow** that list rather than widen the word set.
- The project's `addopts = "-q"` means an agent passing its own `-q` to pytest loses the summary
  line entirely. Run it bare, or with `-o addopts=`.

### `[manual/live]` outstanding for 030

Six of the nine `[manual/live]` items were discharged by the verify run (the mypy / ruff /
typecheck clauses: 001 DoD-12, 002 DoD-15, 003 DoD-12, 004 DoD-10, 005 DoD-12, 006 DoD-10). Three
need a live browser:

- **003 DoD-11** — through the dev proxy, each of the three routes triggers a browser file download
  and the downloaded file opens as the JSON envelope.
- **005 DoD-11** — an admin clicks Export, a `rphelper-database-….json` file downloads, and the page
  shows only its size.
- **006 DoD-9** — each of the three controls downloads a `rphelper-<granularity>-….json` file.
