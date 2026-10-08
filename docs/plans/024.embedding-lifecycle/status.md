# Feature 024 — embedding-lifecycle

| Step | File                                    | Status  | Verifier | Date |
|------|-----------------------------------------|---------|----------|------|
| 001  | `001.search-tables.md`                  | done    | PASS        | 2026-10-04    |
| 002  | `002.embedding-service.md`              | done    | PASS        | 2026-10-04    |
| 003  | `003.session-index.md`                  | done    | PASS        | 2026-10-04    |
| 004  | `004.memo-write-paths.md`               | done    | PASS        | 2026-10-04    |
| 005  | `005.record-keeping-paths.md`           | done    | PASS        | 2026-10-04    |
| 006  | `006.persona-setup-fanout.md`           | done    | PASS        | 2026-10-04    |
| 007  | `007.coverage-banner.md`                | done    | PASS        | 2026-10-04    |
| 008  | `008.authoring-failure-sentences.md`    | done    | PASS        | 2026-10-04    |

## Files Changed

### Step 001 — the virtual tables, their triggers and the back-fill

- `backend/app/db/search_tables.py` — filled the three frozen bodies. `ensure_fts_tables`
  detects absence per table from `sqlite_master` (`type='table'`, by name), creates the
  missing one, back-fills **only** that one, then re-issues all six
  `CREATE TRIGGER IF NOT EXISTS` statements unconditionally (so a trigger a Sync rebuild
  dropped is restored even when its table survived). `vector_table_dimension` parses
  `FLOAT\s*\[\s*(\d+)\s*\]` out of the vec0 table's stored `sqlite_master.sql`; an absent
  table returns no row, which is the `None` case. `ensure_vector_tables` reads **both**
  declared dimensions first and raises `NoEmbeddingModelError(<fixed message>,
  {"reason": "dimension_mismatch"})` before creating anything, then creates only the
  absent tables at `dimension`; no mismatched table is ever re-declared.
- Trigger shapes settled on: `memo_fts` gets the external-content trio
  (`AFTER INSERT` / `AFTER DELETE` / **`AFTER UPDATE OF body`**, so `is_enabled`,
  `is_forced` and `sort_key` writes never touch the index). `message_fts` gets a
  record-row-conditional set — `AFTER INSERT ... WHEN NEW is a record row`, **one**
  `AFTER UPDATE OF text, settled_at, related_to` trigger whose two
  `INSERT ... SELECT ... WHERE` statements run `'delete'` on OLD (only when OLD was a
  record row) and then insert NEW (only when NEW is one), and
  `AFTER DELETE ... WHEN OLD is a record row`. Back-fill is `'rebuild'` for `memo_fts` and
  an explicit `INSERT ... SELECT id, text FROM messages WHERE settled_at IS NOT NULL AND
  related_to IS NULL` for `message_fts`. Private module constants hold the SQL; no new
  public symbol beyond the frozen four constants and three functions.
- `backend/app/services/bootstrap.py` — **no change needed.** The skeleton's edit was
  already final: `ensure_fts_tables(connection)` sits inside the same
  `with connection.begin():`, after `metadata.create_all(connection)` and after the
  `AlreadyConfiguredError` guard, so the refused-create path still leaves an empty
  database and no vector table is created at bootstrap. Verified only.
- Held: nothing added to `db/schema.py`, no `Table(...)` for any of the four virtual
  tables, `session_fts` not created, `errors.py` untouched. Gates from `backend/`:
  `mypy app` → `Success: no issues found in 73 source files`; `ruff check .` →
  `All checks passed!`. pytest not run (the verifier's gate).

### Step 002 — the embedding service and the shared factory dependency

- `backend/app/services/embedding.py` — filled all four frozen bodies; the constant, the
  frozen `EmbeddingModelHandle` and every signature are untouched.
  `open_embedding_model` calls `validate_embedding_model(connection)` (its
  `NoEmbeddingModelError` propagates), re-selects `llm_servers.api_key_ref` by
  `designation.server.id` (the pointer is not a field on `LlmServer`), resolves it with
  `resolve_secret` (its `SecretRefError` propagates **before** any client exists) and calls
  `client_factory(server.base_url, api_key, timeout_seconds)` exactly once — no network
  call, no vector table touched. The re-select is transaction-neutral the way
  `llm_registry._reading` is (roll back only a transaction the read itself autobegan), so a
  caller can still open its own `begin()` afterwards. `embed_texts` is one
  `asyncio.run(client.embed(model_name, texts))` and returns that list unchanged;
  `LlmUnreachableError` is never caught; any vector whose length ≠ `embedding_dim` raises
  `NoEmbeddingModelError(<fixed message>, {"reason": "dimension_mismatch"})`.
  `write_vector` / `delete_vector` resolve the vec0 key column with
  `SELECT name FROM pragma_table_info(:table_name) WHERE pk = 1` (one private helper
  `_key_column` plus its `text()` constant — the only additions beyond the frozen four;
  `rowid` is unusable and the names belong to `001`'s DDL). The upsert is D4's
  delete-then-insert with `sqlite_vec.serialize_float32`; `delete_vector` returns early when
  that query finds no table, ending a transaction it autobegan so the no-op writes nothing.
  Eight deferred imports added exactly as the skeleton listed; no `fastapi` token appears in
  the module (`grep -ic` → 0) and the literal `30.0` appears nowhere.
- `backend/app/dependencies.py` — **no change needed.** The skeleton's D9 move was already
  final: `get_llm_client_factory` returns `LlmClient`, sits after `clear_session_cookie`,
  and no existing symbol moved. Verified only.
- `backend/app/routers/admin_llm.py` — **no change needed.** It imports the dependency from
  `app.dependencies`, defines none of its own, and the nine routes are unchanged. Verified
  only. Re-confirmed by identity:
  `admin_llm.get_llm_client_factory is dependencies.get_llm_client_factory` → `True` and
  `dependencies.get_llm_client_factory() is LlmClient` → `True`, so the delivered
  `dependency_overrides` keyed on the router's name still resolve.
- Behaviour checked with a throwaway probe pointed at a **temp** database
  (`RPHELPER_DATA_DIR` = a `mkdtemp`, `RPHELPER_DB_FILENAME=probe.sqlite`; `backend/data/`
  untouched), since then deleted: one construction with `(base_url, resolved key, 7.5)`;
  zero constructions for not-designated / not-enabled / unset variable; three texts in, three
  vectors out in order from exactly one recorded `embed` call, both on the main thread and in
  a `threading.Thread`; wrong width → `no_embedding_model` + `{"reason":
  "dimension_mismatch"}`; `LlmUnreachableError` through unchanged; for `memo_vec` **and**
  `session_vec` at dim 8 with an id of 1309876543210987654, two writes left one row whose
  blob is byte-identical to `serialize_float32(second)`, delete removed it, and delete of an
  absent id and of an absent table raised nothing.
- Gates from `backend/`: `mypy app` → `Success: no issues found in 73 source files`;
  `ruff check .` → `All checks passed!`. pytest not run (the verifier's gate).

### Step 003 — the session index

- `backend/app/services/session_index.py` — filled the five frozen bodies; no signature,
  docstring or import-posture change. `compose_session_text` reads the session row first with
  `id` **and** `user_id` in its own predicate and returns `""` when that read finds nothing, so a
  foreign or unknown id never reads the character, the setup or the entries (R5); then the
  character `sheet`, the setup `description` **only** when `sessions.setup_id` is not null, then
  `settled_entries.selected_columns` filtered by `session_id` + `user_id` and ordered by `id`
  ascending (`messages.py`'s `_list_session_rows` idiom, R11 — raw `messages` is never selected).
  Parts are collected untrimmed and the result is joined with exactly the two-newline
  separator, dropping any part whose `.strip()` is empty — D6's rule and separator in one
  expression.
- `refresh_session_vectors` runs the pinned order: `ensure_fts_tables` → compose every text into
  a list → split into `pending` (non-empty) and a `delete_vector` per empty text → `return` when
  `pending` is empty (no model opened, no embed call — N = 0 and the all-empty case take the same
  exit) → `open_embedding_model` → `ensure_vector_tables(handle.embedding_dim)` → one
  `embed_texts` over `pending`'s texts → one `write_vector` per session.
- `refresh_session_vector_degraded` wraps the strict call for `(session_id,)` in
  `except (NoEmbeddingModelError, LlmUnreachableError): return True`, with no savepoint and no
  other handler, so `SecretRefError` still propagates (U3) and an empty text returns `False`.
- Both id listers are one `select(sessions.c.id)` with `user_id` plus the second key in the
  predicate, `.order_by(sessions.c.id.asc())`, and **no `archived_at` predicate** (U4).
- Two decisions worth knowing. (1) The composed text of **another user's** session is `""`, so the
  strict refresh takes the empty-text branch for it and calls `delete_vector` on that id — D6's
  rule as written, keyed on the text and not on ownership; nothing is ever *written* for a foreign
  id, and both fan-out listers only ever yield the caller's own ids. (2) `zip(pending, vectors,
  strict=True)` pairs texts to vectors, so a provider returning the wrong *count* raises
  `ValueError` rather than silently skipping a session; a wrong *width* is already
  `NoEmbeddingModelError` inside `embed_texts` (D8), and `ValueError` is deliberately not in the
  degraded catch.
- The private `@contextmanager _reading(connection)` helper (`characters.py`'s form) was added for
  the three read-only functions; a refresh never uses it. No public constant or class was added —
  the module's public surface is exactly the five frozen functions.
- Gates from `backend/`: `mypy app` → `Success: no issues found in 73 source files`;
  `ruff check .` → `All checks passed!`. pytest not run (the verifier's gate).

### Step 004 — the memo write paths

- `backend/app/services/memos.py` — filled the one frozen private seam and added the three
  dispatch conditions the skeleton deliberately left out. No frozen signature changed;
  `reorder_memos` was not touched at all (not its body, not its docstring).
- `_refresh_memo_search_rows` — the body in `004.context.md`'s order: `ensure_fts_tables`
  **unconditionally** (so even a blank-bodied write leaves a pre-024 instance with its
  back-filled full-text tables), then the D7 branch on `body.strip()`. Blank →
  `delete_vector(connection, MEMO_VEC_TABLE, memo_id)` and an early `return`, so no model is
  resolved and the factory is never called. Non-blank → `open_embedding_model(...)` **before**
  `ensure_vector_tables(connection, handle.embedding_dim)` (a missing designation then fails
  before any DDL, a dimension mismatch before any vector row), then one
  `embed_texts(handle, [body])` carrying the body **alone** (US-119), then `write_vector`.
  The single vector is tuple-unpacked — `(vector,) = embed_texts(...)` — so a provider
  answering the wrong count is a `ValueError`, matching step 003's posture. Nothing is
  caught (strict, D8).
- **The three dispatch conditions, as implemented.** (1) `create_memo` calls the helper
  **unguarded** after the insert and read-back — the helper's own blank-body branch is the
  only condition a create needs, which is why a whitespace-only create resolves no model.
  (2) `update_memo` captures `stored_body = memo.body` from the `_require_memo` row that
  already authorises the call — the value **as stored before** the update, read inside the
  same transaction — and then guards the seam with `if body is not None and body !=
  stored_body:`. A flag-only patch and a body resent unchanged (with or without a flag
  change) therefore ensure no table, resolve no model and never construct a client; the
  helper is called with `memo.body`, the value as now stored. (3) `delete_memo` keeps its
  signature and runs `ensure_fts_tables` + `delete_vector(..., MEMO_VEC_TABLE, memo_id)`
  after the `rowcount` check — no model, so it can never answer `no_embedding_model`. The
  ensure sits **after** the relational delete on purpose: a first-ever back-fill then cannot
  re-introduce the row that was just removed.
- Imports: the deferred `from app.db.search_tables import MEMO_VEC_TABLE, ensure_fts_tables,
  ensure_vector_tables` (`app.db`, not a service) and the widened single
  `app.services.embedding` import (`delete_vector`, `embed_texts`, `open_embedding_model`,
  `write_vector` alongside the three names already there). `MEMO_VEC_TABLE` is never
  re-typed as a literal. Re-checked on the final source: `grep -ic` over
  `app/services/memos.py` gives **0** for `title`, **0** for `archived_at`, **0** for
  `fastapi`, and the only `app.services` import is `embedding`.
- `backend/app/routers/memos.py` — **no change needed.** The skeleton's wiring was already
  final: `settings` / `client_factory` appended to `create_own_memo` and `update_own_memo`
  only, each forwarding `client_factory=` and `timeout_seconds=settings.
  llm_request_timeout_seconds`; `GET`, `PUT /api/memos/order`, `DELETE` and the chain route
  untouched; the only `select/update/insert/delete` call is still the `router.delete`
  decorator. Verified, not edited.
- Behaviour checked with two throwaway probes against **temp** databases
  (`RPHELPER_DATA_DIR` = a `mkdtemp`, `RPHELPER_DB_FILENAME=probe.sqlite`; `backend/data/`
  never opened), both since deleted. At dim 8 with snowflake ids: create made exactly one
  factory construction `(base_url, resolved key, 7.5)` and one embed call of exactly
  `['The innkeeper is Kaelith.']`, stored the matching vector and left an FTS `MATCH` on
  "Kaelith" returning the memo id; with no designation → `no_embedding_model`, with a raising
  fake → `llm_unreachable`, and in both cases **no** `memos` row, no vector and no FTS hit
  survived. A changed body replaced the vector; the same call without a designation raised
  and left the stored body and the vector byte-identical. `is_enabled` / `is_forced` /both,
  and a body equal to the stored one plus a flag change, each made **zero** factory
  constructions (with *and* without a designation) and left the vector untouched. A
  whitespace-only create and an update to a blank body both made zero constructions and left
  no `memo_vec` row. A delete with no designation removed the row, its vector and its FTS
  hit. `reorder_memos` made zero constructions and left both vectors identical. On a
  pre-024 database (no virtual tables, two raw-inserted memos) a delete created and
  back-filled `memo_fts` with the **survivor** only and created no vector table, and a
  blank-bodied create on that vector-less database succeeded.
- Gates from `backend/`: `mypy app` → `Success: no issues found in 73 source files`;
  `ruff check .` → `All checks passed!`. pytest not run (the verifier's gate).

### Step 005 — the record-keeping paths and the coverage flag

- `backend/app/services/settle.py` — filled both seams. In `settle` and in `reopen` the
  refresh is now the **last statement inside the existing `with connection.begin():` block**,
  after `_bump_session` and therefore after every relational write, so 003's composition
  observes the new state: settle's head carries its rewritten `settled_text` **and** its
  `settled_at` from the one UPDATE that set both, and a re-opened head has already left
  `settled_entries`. Each assigns `search_coverage_incomplete =
  refresh_session_vector_degraded(connection, user_id, session_id,
  client_factory=client_factory, timeout_seconds=timeout_seconds)` and feeds that boolean into
  the `SettleResult` / `ReopenResult` built after the block (the skeleton's placeholder
  `False` literals are gone). Nothing is caught here — the degraded catch lives inside the
  003 function — so every refusal (`ZoneEmptyError`, `ZoneNotEmptyError`,
  `NothingToReopenError`, `SessionNotFoundError`) still fires before any refresh and before
  any client exists. Held: no `delete(` / `insert(` call was added and the token `delete` /
  `DELETE` appears nowhere in the module (`grep -in` → 0 hits); the only `app.services`
  imports are still `parens`, `llm.chat` and `session_index`; no `fastapi`.
- `backend/app/services/messages.py` — filled both seams. `file_partner_entry` runs the same
  degraded refresh after the insert and the bump, inside its transaction, and passes the
  boolean into the `StreamMessage` it returns.
- **The record-row-vs-zone dispatch in `edit_message_text`, as implemented.** The branch is
  the `message_states` classification the function already made for its own read-back
  selectable — no new predicate, no second query. A buried row (`state.related_to is not
  None`) is still refused before any write, so by the time the dispatch is reached
  `state.settled_at is not None` **is** "this is a record row" (`context.md` Vocabulary) and
  the NULL case is a zone row. The code is `search_coverage_incomplete = False` followed by
  `if state.settled_at is not None:` around the refresh call — written that way round so the
  zone row is the fall-through that touches nothing: it opens no model, constructs no client,
  issues no DDL and leaves any existing `session_vec` row alone. The refresh sits right after
  the `messages` text UPDATE and 023's `translations` discard (order between them immaterial),
  inside the same transaction, so the composition reads the new text. The flag reaches the
  result through `dataclasses.replace(_to_message(row), search_coverage_incomplete=...)`, the
  route the skeleton suggested, leaving the shared `_to_message` untouched for the read paths.
- `append_message` was **not** touched (byte-identical) and its result keeps
  `StreamMessage`'s `False` default, as do every list read, `insert_zone_message`,
  `append_assistant_message` and `services/sessions.py`'s opening message.
- Imports: the deferred widening of the single existing `app.services.session_index` import
  with `refresh_session_vector_degraded` in **both** services, plus `replace` added to
  `from dataclasses import dataclass` in `messages.py`. Re-scanned on the final source:
  `messages.py` contains **no `DELETE`** (case-sensitive, `grep -c` → 0), no `fastapi`, no
  occurrence of `parens`, and its only `app.services` import is still `session_index`; no new
  `select(...)` over `messages` and no new `related_to` / `kind` / `settled_at` assignment.
- `backend/app/models/stream.py` — **no change needed.** The skeleton's three required
  `search_coverage_incomplete: bool` fields were already final; re-verified through
  `app.openapi()`: the field is in `properties` **and** in `required` on `SettleResponse`,
  `ReopenResponse` and `MessageResponse`. Verified only.
- `backend/app/routers/stream.py` — **no change needed.** The skeleton's wiring was already
  final: `get_settings` + the shared `get_llm_client_factory` on exactly `file_partner`,
  `settle_zone`, `reopen_group` and `edit_message`, each forwarding `client_factory=` and
  `timeout_seconds=settings.llm_request_timeout_seconds`; the two mappers pass the result's
  flag; `_message_to_response` and every other handler (including the zone append, which
  answers `false` from the default — the "Router note") untouched. Verified only.
- Behaviour checked with a throwaway probe against **temp** databases
  (`RPHELPER_DATA_DIR` = a `mkdtemp`, `RPHELPER_DB_FILENAME=probe.sqlite`;
  `backend/data/rphelper.sqlite` never opened — its mtime was unchanged), since deleted. At
  dim 8 with snowflake ids and a recording fake: settle with a designation → flag `False`,
  one construction `(base_url, resolved key, 7.5)`, one embed call of the composed text
  `'<sheet>\n\n<settled text>'`, a `session_vec` blob byte-identical to the expected vector
  and the settled text found through `message_fts MATCH`. Settle with **no** designation and
  settle with a raising fake → the entry is settled, the zone is empty, flag `True`, and no
  vector row exists. Settle-then-re-open → both flags `False`, and the row after re-open
  matches the vector of a composed text that no longer contains the re-opened entry. A
  settled-entry edit (turn, decision and a settled partner block) → flag `False`, the stored
  text is the new one and the row matches the new composed text; the same edit with the
  designation removed → the text still saves and is returned, flag `True`, and the
  pre-existing blob is **byte-identical**. A zone `append_message` and a zone-row edit with a
  designation present → **zero** factory constructions, zero embed calls, both flags `False`
  and the existing vector unchanged. `file_partner_entry` → flag `False` with the filed text
  inside the embedded composition; with no designation the row is still filed settled with
  `kind='partner'` and the flag is `True`. Every refusal path (zone-empty settle, buried edit,
  missing id, foreign session) raised as before with zero constructions and no vector table.
- Gates from `backend/`: `mypy app` → `Success: no issues found in 73 source files`;
  `ruff check .` → `All checks passed!`; `create_app()` + `app.openapi()` build (no import
  cycle from the new `settle.py` / `messages.py` → `session_index` edge). pytest not run (the
  verifier's gate).

### Step 006 — the persona and setup fan-out

- `backend/app/services/characters.py` — filled the one seam in `update_character`. The
  deferred import widening landed exactly as frozen: the single
  `from app.services.session_index import ...` now also brings `refresh_session_vectors` and
  `session_ids_for_character`, and nothing else — no `app.db.search_tables`, no `app.errors`
  addition and still exactly one `app.services` import.
- **The persona dispatch, as implemented.** Immediately after the owner-scoped
  `_require_character(...)` that the update already needs to authorise, the pre-update value
  is captured as `stored_sheet = character.sheet`. That is the only moment it is still the old
  one — `character` is reassigned by `_fetch_existing` after the UPDATE — so nothing is
  re-read later. The fan-out is then the **last statement inside the existing
  `with connection.begin():` block**, after the `if supplied:` write, so each composed session
  text observes the sheet just written. The condition is
  `if sheet is not None and sheet != stored_sheet:` — a sheet that was not supplied and a
  sheet resent byte-identical to the stored one both fall through, which is exactly D5's
  name-only edit. Inside it, `session_ids = session_ids_for_character(connection, user_id,
  character_id)` (ascending id, archived sessions included, no archive predicate), and then
  `if session_ids:` guards the single
  `refresh_session_vectors(connection, user_id, session_ids, client_factory=client_factory,
  timeout_seconds=timeout_seconds)` call, so N = 0 skips the call entirely and resolves no
  model. Strict (D8): there is no `try` anywhere in the function, so `NoEmbeddingModelError`
  and `LlmUnreachableError` propagate out of the `with` block, the transaction rolls back and
  the persona edit is not stored.
- `backend/app/services/setups.py` — the same seam, the same shape: `stored_description =
  setup.description` captured at `_require_setup`, the dispatch
  `if description is not None and description != stored_description:`, then
  `session_ids_for_setup(connection, user_id, setup_id)` (whose `setup_id` equality excludes a
  sibling setup's and a setup-less session on its own) and the same `if session_ids:` guard
  around the one strict `refresh_session_vectors` call, last in the `with` block. Its import
  widening added `refresh_session_vectors` and `session_ids_for_setup` to the same single
  `app.services.session_index` import.
- `create_character`, `create_setup`, `archive_*` and `restore_*` are **byte-identical** — no
  create, archive or restore path can now need a model. No new symbol was added to either
  module, and no frozen signature changed.
- **Source-scan guards re-verified on the final source.** `grep -ci delete` →
  **0 for `app/services/characters.py` and 0 for `app/services/setups.py`**: the substring
  `delete` does not occur anywhere in either file, case-insensitively, comments and docstrings
  included (every added comment was written around the word deliberately; the fan-out reaches
  the vector removal only indirectly, through `session_index`, a different file). Also still
  0: `grep -ci fastapi` in both, and `app.services.characters` anywhere in `setups.py` (its
  `from app` imports are exactly `app.db.schema`, `app.errors`, `app.ids`,
  `app.services.session_index`).
- `backend/app/routers/characters.py`, `backend/app/routers/setups.py` — **no change needed.**
  The skeleton's wiring was already final and was verified only: each PATCH handler takes
  `settings: Annotated[Settings, Depends(get_settings)]` and
  `client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)]` and forwards
  `client_factory=client_factory, timeout_seconds=settings.llm_request_timeout_seconds`; no
  other handler in either router was touched.
- Behaviour checked with two throwaway probes against **temp** databases
  (`RPHELPER_DATA_DIR` = a `mkdtemp`, `RPHELPER_DB_FILENAME=probe006*.sqlite`;
  `backend/data/rphelper.sqlite` never opened — its mtime was unchanged), since deleted. With
  a character carrying one session and **no** designated model: a name-only edit, and an edit
  resending the stored sheet with a new name, both succeeded with **zero** client-factory
  constructions; the same two for a setup's description. A changed sheet and a changed
  description each raised `NoEmbeddingModelError` and left the stored sheet / description the
  old one. A character with no sessions and a setup no session uses each stored the changed
  text with **zero** constructions (N = 0). With a designated model at dim 8 and a recording
  fake, over four snowflake-id sessions (setup X active, setup X archived, setup Y, no setup),
  each with a settled entry: the persona edit made **one** factory construction and **one**
  `embed` call carrying all four composed texts, each beginning with the new sheet, and wrote
  a `session_vec` row for all four ids; X's description edit then made one construction and
  one `embed` call carrying exactly **two** texts, both containing the new description.
- Gates from `backend/`: `mypy app` → `Success: no issues found in 73 source files`;
  `ruff check .` → `All checks passed!`. pytest not run (the verifier's gate).

### Step 007 — the coverage flag and the banner

- `frontend/src/app/streamState.ts` — replaced the five frozen seams with the real flag
  writes, and deleted the five `void <captured>;` statements that existed only for
  `noUnusedLocals`. Nothing else in the module changed: the observable field
  `searchCoverageIncomplete = false` was already declared as frozen, the type import already
  named `ReopenResult` / `SettleResult`, no import was added, no export was added or removed,
  all five effect signatures are untouched, and the class still holds data only — every write
  lives in a free effect function, inside a `runInAction`.
- **Where each write sits, per effect.**
  - `settleComposer` — after the settle's `try`/`catch` and the `if (signal?.aborted) return;`,
    **before** `rereadBoth`, guarded `if (settled !== undefined)`. From the `SettleResult`.
  - `reopenLast` — the same position relative to its own request and `rereadBoth`, guarded
    `if (reopened !== undefined)`. From the `ReopenResult`.
  - `sendComposer` (partner branch) — after `clearDraftIfUnchanged`, before `rereadEntries`,
    guarded `if (filed !== undefined && filed.settled_at !== null)`. From the returned
    `Message`.
  - `filePastedPartner` — the same position and the same two-part guard, before its
    `rereadEntries`.
  - `editEntry` — **inside the existing `runInAction` on the settled path**, as the second
    statement after the `state.entries` map, so it is reached only past the
    `updated.settled_at === null` early return. That early return was left exactly as it was
    (only its comment now names D11), which is what gives D11's "a zone-row response leaves
    the flag unchanged" without any write before it.
- **How an absent field reads as `false`.** Every write is
  `… .search_coverage_incomplete ?? false`, so a successful response carrying no field writes
  `false` and therefore **clears** a previously-true flag (D10). In the four effects whose
  result is a `let … | undefined`, the value is read into a `const incomplete` **before** the
  `runInAction`, because TypeScript's narrowing of a `let` does not survive into the closure;
  `editEntry`'s `updated` is a definitely-assigned `Message`, so it is read inline.
- **No flag write in any `catch`, and none for a zone row** (D11): a failed request falls
  through every guard with its captured variable still `undefined`, and a returned row with a
  null `settled_at` fails the `settled_at !== null` half. `editZoneMessage` was not touched.
  Every failure path, notification, `busy` transition, abort check and re-read is byte-identical.
- `frontend/src/app/streamApi.ts` — **no change needed.** Verified only: `Message` carries
  `search_coverage_incomplete?: boolean` as its twelfth key after `tool_args`, and
  `SettleResult` / `ReopenResult` each carry it as their last key; all nine calls and the three
  private response types are untouched.
- `frontend/src/app/SessionStream.tsx` — **no change needed.** Verified only: the non-exported
  module-level `COVERAGE_BANNER_TEXT` holds `007.context.md`'s sentence verbatim, and the
  inline `{state.searchCoverageIncomplete ? <Alert role="alert" color="yellow">…</Alert> : null}`
  is the first child of the ready branch's `<Stack gap="md">`, immediately before
  `<StreamRecord …>`. `Alert` is in the existing `@mantine/core` import, no close button, no
  title, no icon, no new prop, and 023's translation lines are intact.
- Gate from `frontend/`: `npm run typecheck` → clean, both projects (`tsconfig.json` and
  `tsconfig.node.json`), no output. `npm test` not run (the verifier's gate).

### Step 008 — the authoring-failure sentences

- `frontend/src/shared/embeddingFailure.ts` — **no change needed.** Verified only: the skeleton
  delivered it in full. `embeddingFailureSentence(error: unknown): string | null` guards with
  `isApiError` from `./apiError`, compares `code` only (never `status`), answers
  `NO_EMBEDDING_MODEL_SENTENCE` / `LLM_UNREACHABLE_SENTENCE` and null for everything else; both
  exported constants hold `008.context.md`'s text verbatim; the two code constants stay
  non-exported; the only import is the relative `./apiError`. Grep-confirmed: no `@mantine/*`
  import, and no `parseInt` / `Number.parseInt` / `<name>: number`-shaped text anywhere in the
  file, comments included.
- **The four substitutions** — in each catch the frozen seam's `const refusal: string | null =
  null;` became `const refusal: string | null = embeddingFailureSentence(error);`, the
  `void error;` line (present in three of the four) was deleted, and the SEAM comment was
  replaced by a one-sentence statement of the rule. **Nothing else moved:** no signature, no
  export, no observable field, no success path, no `busy` / `saving` transition, no abort guard
  and no other catch.
  - `frontend/src/app/memoLevelState.ts` — `saveNote`'s **body-PATCH** catch (writes
    `state.failures[memoId]`) and `saveNewNote`'s **POST** catch (writes `state.newNote.failure`,
    keeping the typed text). Added `import { embeddingFailureSentence } from
    "../shared/embeddingFailure";`.
  - `frontend/src/app/characterScreenState.ts` — `commitPersona`'s catch (writes `state.error`),
    per `## Ultra phase` (3): the character surface is `commitPersona`, not the non-existent
    `submitSave`. Same import added after the existing `../shared/apiError` one.
  - `frontend/src/app/setupDraft.ts` — `submitSetup`'s catch (writes `draft.error`), covering
    both the create and the save branch. It already bound `error` for its abort guard, which is
    untouched and still returns first. Same import added.
- **The generic fallback is preserved in all four**, because the `refusal ?? <generic>` shape the
  skeleton froze was kept verbatim: `"Could not save the note."` (both memo catches),
  `"Could not save the character."` (`commitPersona`), and `submitSetup`'s `failureMessage`
  local — `"Could not create the setup."` when `draft.original === null`, else
  `"Could not save the setup."`, still chosen **before** the request, with the helper's sentence
  only taking precedence when it returns one.
- **Deliberately untouched, per D5:** `saveNote`'s blank→DELETE branch
  (`"Could not delete the note."`, still a bare `catch {`), the two flag toggles, the reorder,
  `commitName` and `submitCreate`. None of those does vector work, so none can receive
  `no_embedding_model` or `llm_unreachable`.
- Gate from `frontend/`: `npm run typecheck` → clean, both projects (`tsconfig.json` and
  `tsconfig.node.json`), no output. `npm test` not run (the verifier's gate).

## Skeleton

### Step 001 — frozen interface (2026-10-04)

`backend/app/db/search_tables.py` — new module. Four module-level table-name constants,
declared with their real values (later steps import them, never re-type the names):

- `MEMO_FTS_TABLE = "memo_fts"` — new
- `MESSAGE_FTS_TABLE = "message_fts"` — new
- `MEMO_VEC_TABLE = "memo_vec"` — new
- `SESSION_VEC_TABLE = "session_vec"` — new

Three functions, bodies `raise NotImplementedError`:

- `backend/app/db/search_tables.py` — `ensure_fts_tables(connection: Connection) -> None` — new
- `backend/app/db/search_tables.py` — `vector_table_dimension(connection: Connection, table_name: str) -> int | None` — new
- `backend/app/db/search_tables.py` — `ensure_vector_tables(connection: Connection, dimension: int) -> None` — new

`Connection` is `sqlalchemy.Connection` (Core), the project's convention of connection-first.
`table_name` is deliberately plain `str`, not a `Literal`, so `025` can pass either vector
name through a variable.

`backend/app/services/bootstrap.py` — `create_first_administrator(connection, generator,
username, password, ttl_hours) -> BootstrapResult` — **signature and return unchanged**
(the pinned parameter list is untouched). Real edit, not a stub:

- added `from app.db.search_tables import ensure_fts_tables`;
- inside `with connection.begin():`, **after** `metadata.create_all(connection)` and after
  the `AlreadyConfiguredError` guard, added `ensure_fts_tables(connection)` with a four-line
  comment explaining D2 and why the call sits inside the guarded block (harvest F8 item 2:
  the refused-create path must still leave `_table_names(db_engine) == set()`, so nothing
  may create a table before or outside the guard);
- the function docstring now names the ensure step and states that no vector table is
  created at bootstrap.

Nothing was added to `db/schema.py`; no `Table(...)` exists for the four virtual tables;
`session_fts` is not created; `errors.py` is untouched.

- Caller-compile edits (out of Source-files scope): None.

### Gates (from `backend/`)

- `.venv/Scripts/python -m mypy app` — `Success: no issues found in 71 source files`
- `.venv/Scripts/python -m ruff check .` — `All checks passed!`
- pytest deliberately not run (red gate is the verifier's).

### Deferred imports the coder must add to `search_tables.py`

Omitted from the stub because `ruff` F401 rejects an unused import. The stub currently
imports only `from sqlalchemy import Connection`:

- `from app.errors import NoEmbeddingModelError` — raised by `ensure_vector_tables` on a
  dimension mismatch, with a fixed message (the class has **no** default message, harvest C)
  and `detail={"reason": "dimension_mismatch"}` (D8).
- `from sqlalchemy import text` — for the `sqlite_master` probe, the DDL and the back-fill.
- `import re` — for the `FLOAT[n]` read-back.

### Observed facts the coder binds to (throwaway probe, deleted; 2026-10-04)

1. **DDL inside `with connection.begin():` genuinely rolls back.** Through the project's own
   `get_engine`, one block created a base table, `memo_fts` (fts5 external content), a
   trigger and `memo_vec` (`vec0`), then raised. After the rollback `sqlite_master` was
   **completely empty** — no virtual table, no trigger, and no fts5/vec0 shadow table. DoD-7
   is therefore achievable with no cleanup code.
2. **The exact `sqlite_master.sql` a `vec0` table stores** is the `CREATE` statement
   **verbatim as issued**, whitespace and case included. For a committed
   `CREATE VIRTUAL TABLE memo_vec USING vec0(memo_id INTEGER PRIMARY KEY, embedding FLOAT[8])`
   the stored `sql` read back as exactly:

   ```
   CREATE VIRTUAL TABLE memo_vec USING vec0(memo_id INTEGER PRIMARY KEY, embedding FLOAT[8])
   ```

   and `session_vec` at 768 as `... embedding FLOAT[768])`. So `vector_table_dimension` parses
   `FLOAT[<digits>]` out of that text; a tolerant case-insensitive pattern allowing optional
   whitespace (`FLOAT\s*\[\s*(\d+)\s*\]`) is the safe form, since the text is only ever
   whatever this module itself wrote. A `SELECT sql FROM sqlite_master WHERE type='table' AND
   name=?` for an absent table returns **no row** (not a NULL `sql`), which is the `None` case.
3. Shadow tables observed (all `type='table'`, relevant to any test that reads
   `sqlite_master`): fts5 adds `_data`, `_idx`, `_content` (only when not external content),
   `_docsize`, `_config`; vec0 adds `_info`, `_chunks`, `_rowids`, `_vector_chunks00`, plus
   `sqlite_sequence` and four `sqlite_autoindex_*` index rows. vec0's shadow tables carry no
   readable dimension column, which is why the DDL text is the read-back source.

### Step 002 — frozen interface (2026-10-04)

#### `backend/app/services/embedding.py` — new module

One constant, one frozen dataclass and four functions. Every function body is
`raise NotImplementedError`; the constant and the dataclass are real.

- `DEFAULT_EMBED_TIMEOUT_SECONDS: Final[float]` — **new**. Declared as:

  ```python
  DEFAULT_EMBED_TIMEOUT_SECONDS: Final[float] = Settings.model_fields[
      "llm_request_timeout_seconds"
  ].default
  ```

  **How the default is derived:** read off the pydantic field declaration in
  `app/config.py` at import time (`from app.config import Settings`), never re-typed. The
  literal `30.0` appears nowhere in `embedding.py`. Verified: the expression evaluates to
  `30.0`, a real `float`, and `mypy` accepts it against the `Final[float]` annotation
  (`FieldInfo.default` is `Any`). `Settings` is only *imported*, never *instantiated* and
  `get_settings` is never called — the services' no-settings-lookup rule holds.
  **If a test wants the expected value it must read the same field, not write `30.0`.**

- `@dataclass(frozen=True) class EmbeddingModelHandle` — **new**. Three fields, in this
  order (so positional construction works):

  | Field | Type |
  |---|---|
  | `client` | `LlmClientLike` (the registry's Protocol, `app.services.llm_registry`) |
  | `model_name` | `str` |
  | `embedding_dim` | `int` |

- `open_embedding_model(connection: Connection, *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> EmbeddingModelHandle`
  — **new**. `client_factory` and `timeout_seconds` are **keyword-only with defaults**,
  per D9 and matching `designate_embedding_model`'s existing `*, client_factory:
  LlmClientFactory = LlmClient`. Callers must pass them by keyword.
- `embed_texts(handle: EmbeddingModelHandle, texts: Sequence[str]) -> list[list[float]]`
  — **new**. `texts` is `collections.abc.Sequence[str]`, so a `list` or a `tuple` binds.
- `write_vector(connection: Connection, table_name: str, row_id: int, vector: Sequence[float]) -> None`
  — **new**. All four positional.
- `delete_vector(connection: Connection, table_name: str, row_id: int) -> None` — **new**.
  All three positional.

Type notes the coder and test-coder both bind to:

- `Connection` is `sqlalchemy.Connection` (Core), connection-first, as everywhere else.
- `table_name` is plain `str`, not a `Literal` — matching step 001's
  `vector_table_dimension`, so either of `MEMO_VEC_TABLE` / `SESSION_VEC_TABLE` passes
  through a variable.
- `vector: Sequence[float]` accepts the `list[float]` elements of `embed_texts`' return
  directly.
- `LlmClientFactory` is the registry's `Callable[[str, str | None, float], LlmClientLike]`.
  The default is the class `LlmClient` itself (`app.services.llm.client`), which mypy
  accepts as that callable — the same arrangement `llm_registry` already relies on.
- **`resolve_secret`'s error class is `app.errors.SecretRefError`** (`code =
  "secret_ref_missing"`, `http_status = 500`). For an unset variable it carries
  `detail={"variable": <name>}`; the malformed-`$NAME` case carries no detail. DoD-3's
  "the `secret_ref_missing` error" is that class, imported from `app.errors`.
- The module imports nothing from the web framework. Its docstring deliberately avoids the
  literal token `fastapi` (verified absent from the source, case-insensitively), so DoD-10
  is satisfiable either by the project's established **AST import walk**
  (`test_bootstrap_service.py:529-548`, the idiom to copy) or by a naive substring scan.

#### `backend/app/dependencies.py` — real edit, not a stub

- `get_llm_client_factory() -> LlmClientFactory` — **new here, moved verbatim** from
  `app/routers/admin_llm.py` (body `return LlmClient`, docstring unchanged). Appended at
  the end of the module, after `clear_session_cookie`, so the cookie pair stays adjacent.
- Two imports added: `from app.services.llm.client import LlmClient` and
  `from app.services.llm_registry import LlmClientFactory`.
- Module docstring gained one paragraph saying why a non-auth dependency now lives here
  (D9) and that `admin_llm` re-exports the same object.
- No existing symbol in this file changed. No circular import: `llm_registry` and
  `llm/client` import no `app.dependencies`.

#### `backend/app/routers/admin_llm.py` — real edit, not a stub

- The six-line `def get_llm_client_factory()` definition is **deleted**.
- `from app.dependencies import require_role` → `from app.dependencies import
  get_llm_client_factory, require_role`.
- `from app.services.llm.client import LlmClient` **removed** — after the move it was this
  module's only use of the name, so ruff F401 would have rejected it.
- `from app.services.llm_registry import (... LlmClientFactory ...)` **kept**: still used
  in the three `Annotated[LlmClientFactory, Depends(get_llm_client_factory)]` parameters
  (unchanged, as are all nine routes).
- The docstring's "Test seam" paragraph now says the dependency lives in `app.dependencies`
  and that the name here is an import of the same object.

**Identity check performed** (run under `backend/`, `.venv/Scripts/python -c ...`):

| Assertion | Result |
|---|---|
| `admin_llm.get_llm_client_factory is dependencies.get_llm_client_factory` | `True` |
| `get_llm_client_factory.__module__` / `__qualname__` | `app.dependencies` / `get_llm_client_factory` |
| `dependencies.get_llm_client_factory() is LlmClient` | `True` |
| after `create_app()` and `overrides[admin_llm.get_llm_client_factory] = …`, is `dependencies.get_llm_client_factory in overrides` | `True` |

The last row is the one that matters for DoD-11: `test_admin_llm_router.py`'s existing
`app.dependency_overrides[get_llm_client_factory] = lambda: fake` (both the `application`
and `guarded_probe_app` fixtures) keys the *same* dict entry the routes now resolve, so
those tests pass **with no edit at all** — only their import line could ever need changing,
and it does not, because the name is still re-exported from `app.routers.admin_llm`.

#### Gates (from `backend/`)

- `.venv/Scripts/python -m mypy app` — `Success: no issues found in 72 source files`
- `.venv/Scripts/python -m ruff check .` — `All checks passed!`
- pytest deliberately not run (the red gate is the verifier's).

#### Deferred imports the coder must add to `embedding.py`

Omitted because ruff F401 rejects an unused import. The stub currently imports only
`Sequence`, `dataclass`, `Final`, `Connection`, `Settings`, `LlmClient`,
`LlmClientFactory`, `LlmClientLike`.

- `import asyncio` — the one `asyncio.run` in `embed_texts` (D1).
- `import sqlite_vec` — `sqlite_vec.serialize_float32(...)` in `write_vector`.
- `from sqlalchemy import select, text` — the `api_key_ref` re-select and the vector DML /
  existence probe.
- `from app.db.schema import llm_servers` — the re-select's table.
- `from app.errors import NoEmbeddingModelError` — the dimension-mismatch raise. The class
  has **no** default message, so pass a fixed message plus
  `detail={"reason": "dimension_mismatch"}` (D8).
- `from app.secrets import resolve_secret` — resolving `api_key_ref`.
- `from app.services.llm_registry import validate_embedding_model` — widen the existing
  `llm_registry` import; this step is its **first** call site in `app/` (harvest B7).

#### Observed facts the coder binds to (throwaway probe, deleted; 2026-10-04)

Run through the project's own `get_engine`, SQLite 3.47.1 / sqlite-vec 0.1.9, against
`CREATE VIRTUAL TABLE memo_vec USING vec0(memo_id INTEGER PRIMARY KEY, embedding FLOAT[8])`
with `BIG = 1309876543210987654` (> 2^60).

1. **D4 is necessary, not stylistic — confirmed.** On an id already present:
   - `INSERT OR REPLACE INTO memo_vec(memo_id, embedding) VALUES (?, ?)` →
     `sqlite3.OperationalError: UNIQUE constraint failed on memo_vec primary key`;
   - `INSERT OR IGNORE …` → **the same error** (vec0 0.1.9 ignores the conflict clause
     entirely, so no `ON CONFLICT` spelling is a way out);
   - plain `INSERT …` → the same error, as expected.

   On a *brand-new* id `INSERT OR REPLACE` succeeds, which is exactly why the bug hides
   until the second write of the same row.

2. **The working upsert form** (both statements inside the caller's one transaction,
   `rowcount` in brackets):

   ```sql
   DELETE FROM memo_vec WHERE memo_id = :id;                             -- [1] or [0]
   INSERT INTO memo_vec(memo_id, embedding) VALUES (:id, :blob);         -- [1]
   ```

   Run twice in a row for the same snowflake id, this left **exactly one row** holding the
   **second** vector, `count(*) == 1`. `UPDATE memo_vec SET embedding = :blob WHERE
   memo_id = :id` also works (`rowcount 1`) but is only valid where the row is known to
   exist, which `write_vector` cannot assume. `:blob` is `sqlite_vec.serialize_float32(v)`,
   bound as a plain parameter through `sqlalchemy.text(...)` with no type decoration.

3. **Point lookup by snowflake id round-trips exactly.**
   `SELECT memo_id, embedding FROM memo_vec WHERE memo_id = :id` returned one row;
   `row[0] == BIG` is `True` (no precision loss at 1.3e18), and `row[1]` came back as
   `bytes` of length `4 * dim` **byte-identical** to `serialize_float32(vector)`. So a test
   may compare the stored blob to `serialize_float32(expected)` directly, or unpack it with
   `struct.unpack("<8f", blob)`.

4. **`rowid` is NOT usable on these tables — this shapes the implementation.** Because the
   vec0 DDL names its key column (`memo_id` / `session_id`), every `rowid` spelling fails:
   `INSERT INTO memo_vec(rowid, …)` → `table memo_vec has no column named rowid`, and
   `WHERE rowid = ?` → `no such column: rowid`. `PRAGMA table_info(memo_vec)` shows exactly
   two columns, `memo_id` (pk) and `embedding`.

   `write_vector` / `delete_vector` take a table name and no column name, so the coder must
   resolve the key column from the table. The probed, parameter-safe way:

   ```sql
   SELECT name FROM pragma_table_info(:table_name) WHERE pk = 1
   ```

   — the table-valued form accepts a **bound** parameter (bare `PRAGMA` does not), returned
   `[('memo_id', 1), ('embedding', 0)]` for a present table and **`[]` for an absent one**.
   That single query therefore answers both "what is the key column" and "does the table
   exist", which is `delete_vector`'s whole tolerance in one round trip. A hard-coded
   `{MEMO_VEC_TABLE: "memo_id", SESSION_VEC_TABLE: "session_id"}` map is the alternative but
   re-types names that step 001's DDL owns; the pragma read is preferred.

5. **`delete_vector`'s two tolerances, measured.**
   - absent row: `DELETE FROM memo_vec WHERE memo_id = 42` → `rowcount 0`, **no error**;
   - absent table: `DELETE FROM session_vec WHERE session_id = ?` →
     `sqlite3.OperationalError: no such table: session_vec`, so it **must** be guarded.
     Either the `pragma_table_info` read above or
     `SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :n` (returned `None` for
     the absent table) works as the guard.

### Step 003 — frozen interface (2026-10-04)

#### `backend/app/services/session_index.py` — new module

Five functions, no constants and no classes. Every body is `raise NotImplementedError`.
Signatures verbatim (all parameters positional except the two D9 keyword-only ones):

- `compose_session_text(connection: Connection, user_id: int, session_id: int) -> str` — **new**
- `refresh_session_vectors(connection: Connection, user_id: int, session_ids: Collection[int], *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> None` — **new**
- `refresh_session_vector_degraded(connection: Connection, user_id: int, session_id: int, *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> bool` — **new**
- `session_ids_for_character(connection: Connection, user_id: int, character_id: int) -> list[int]` — **new**
- `session_ids_for_setup(connection: Connection, user_id: int, setup_id: int) -> list[int]` — **new**

Type notes the coder and test-coder both bind to:

- `Connection` is `sqlalchemy.Connection` (Core), connection-first, `user_id` second — the
  project's convention, and `settle.py` / `messages.py`' shape exactly.
- **`session_ids` is `collections.abc.Collection[int]`**, not `Sequence` and not `set`: the
  strict refresh needs only "iterate it and know whether it is empty", so a `list`, a
  `tuple` and a `set` all bind. This is what lets step 006 pass either lister's return value
  straight through, and what lets a test pass `[]` for the N = 0 case.
- **`refresh_session_vector_degraded` returns `bool` where `True` means coverage is
  INCOMPLETE** (the sense the wire's `search_coverage_incomplete` carries). Empty text
  returns `False` (complete, D6).
- `client_factory` / `timeout_seconds` are **keyword-only with defaults**, byte-identical in
  both refresh functions and identical to `open_embedding_model`'s (D9). Verified at
  runtime: `client_factory`'s default **is** `app.services.llm.client.LlmClient` and
  `timeout_seconds`' default evaluates to `30.0`, read from
  `app.services.embedding.DEFAULT_EMBED_TIMEOUT_SECONDS` — the literal `30.0` appears
  nowhere in this module. A test wanting the expected timeout must read the same name.

**The return type of the two id listers — the deliberate choice: `list[int]`, ascending
`id`.** `set[int]` was the alternative, since DoD-10 compares the results as sets, and it
was rejected: a `list` keeps the fan-out's order deterministic, so the **one** `embed_texts`
call of a persona or setup refresh carries its N texts in a reproducible order (D1), which a
`set` would leave to hash order. Both docstrings pin "ascending `id`", and the `Collection`
parameter above means a `list` feeds `refresh_session_vectors` unchanged. DoD-10's set
comparison is unaffected — `set(session_ids_for_character(...)) == {S1, S2, S3, S4}` — and
nothing in the plan asks for a set-typed return. Duplicate ids are impossible either way
(one row per session).

How the frozen interface binds to 001 / 002 (no frozen signature was changed, nothing
outside the one Source file was touched):

- step 001: `ensure_fts_tables(connection)`, `ensure_vector_tables(connection, dimension)`,
  `SESSION_VEC_TABLE`;
- step 002: `open_embedding_model(connection, *, client_factory=..., timeout_seconds=...)`,
  `embed_texts(handle, texts)`, `write_vector(connection, table_name, row_id, vector)`,
  `delete_vector(connection, table_name, row_id)` — the last one's absent-table tolerance is
  what lets step 3 of the strict refresh run on a database with no vector table.

**Import posture — `fastapi` absent, and only one `app.services.` import.** Verified by an
AST import walk over the module source: the imported modules are exactly
`collections.abc`, `sqlalchemy` and `app.services.embedding`, so the single `app.services.`
import is `embedding` as the Interface intent requires, and the token `fastapi` does not
occur in the source at all (case-insensitive `grep` finds 0 lines) — DoD-12 is satisfiable
by either the AST walk (`test_bootstrap_service.py:529-548`, the idiom to copy) or a naive
substring scan.

**One consequence the coder must not "clean up":** `LlmClient` and `LlmClientFactory` are
imported **from `app.services.embedding`**, which re-exports them, not from
`app.services.llm.client` / `app.services.llm_registry` directly. That is deliberate — a
direct import would make this module import three services instead of one and break the
invariant above. mypy accepts it (the project does not enable `no_implicit_reexport`), and
runtime identity was checked: the default **is** the same `LlmClient` class object.

- Caller-compile edits (out of Source-files scope): None. The module is new and has no
  caller yet (005 and 006 add them).

#### Gates (from `backend/`)

- `.venv/Scripts/python -m mypy app` — `Success: no issues found in 73 source files`
- `.venv/Scripts/python -m ruff check .` — `All checks passed!`
- pytest deliberately not run (the red gate is the verifier's).

#### Deferred imports the coder must add to `session_index.py`

Omitted from the stub because ruff F401 rejects an unused import. The stub currently imports
only `Collection`, `Connection`, and `DEFAULT_EMBED_TIMEOUT_SECONDS` / `LlmClient` /
`LlmClientFactory` from `app.services.embedding`.

- `from sqlalchemy import select` — the session row, the character `sheet`, the setup
  `description`, the `settled_entries` read and both fan-out selections.
- `from app.db.schema import characters, sessions, settled_entries, setups` — R11: the
  entries read goes through the **`settled_entries` selectable** (`select(messages).where(
  settled_at IS NOT NULL)`, a Core selectable and not a SQL view), used as
  `settled_entries.selected_columns` then `settled_entries.where(cols.session_id == …,
  cols.user_id == …).order_by(cols.id.asc())` — `messages.py`'s `_list_session_rows` idiom.
  Raw `messages` is never selected here.
- `from app.db.search_tables import SESSION_VEC_TABLE, ensure_fts_tables, ensure_vector_tables`
  — the step-001 half. The table name is imported, never re-typed.
- `from app.errors import LlmUnreachableError, NoEmbeddingModelError` — the degraded catch
  only; this module **raises** neither, and `errors.py` is not touched.
- widen the `app.services.embedding` import with `delete_vector`, `embed_texts`,
  `open_embedding_model`, `write_vector` (and `EmbeddingModelHandle` if the coder annotates
  a local).
- `from collections.abc import Iterator` + `from contextlib import contextmanager` **only
  if** the coder adds the project's private `_reading(connection)` helper
  (`characters.py:222`, `llm_registry.py:308`) so the read-only functions end the
  autobegun transaction they opened when the caller had none. A refresh must **not** use it
  — it runs inside the caller's transaction.

#### Interface facts the coder must preserve (from `003.context.md`, not re-derivable later)

- **Order inside a refresh:** ensure FTS → compose all → delete the rows of empty texts →
  (only if anything is non-empty) open the model → ensure the vector tables → one
  `embed_texts` → write. Opening the model **before** the vector ensure is what makes a
  missing designation fail before any DDL; ensuring **before** writing is what makes a
  dimension mismatch fail before any vector write.
- **No savepoint** around the degraded catch: both raise points are Python-level, no SQL
  statement failed, so the caller's SQLite transaction is intact and still usable.
- A `secret_ref_missing` (`SecretRefError`) raised while opening the model is **not**
  caught by the degraded path (U3's list). `outcome.md` flags it as an open item.
- `sessions` has **no** `title` / `partner_label` column, `characters.sheet` is `Text NOT
  NULL` and may be `""`, `setups.description` is `Text NOT NULL`, `sessions.setup_id` is
  nullable. No `archived_at` predicate occurs anywhere in this module (U4).

### Step 004 — frozen interface (2026-10-04)

#### `backend/app/services/memos.py` — real edits to delivered functions, plus one new private helper

Two signatures changed, each by **adding the same keyword-only pair** (024 D9) and nothing
else. Positional inputs, defaults and return types are untouched, so every existing
positional call still binds (verified at runtime; `routers/memos.py` is the only caller in
`app/`):

- `create_memo(connection: Connection, generator: SnowflakeGenerator, user_id: int, scope: MemoScope, scope_id: int | None, body: str, *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> Memo`
  — **changed** (was `create_memo(connection, generator, user_id, scope, scope_id, body) -> Memo`).
- `update_memo(connection: Connection, user_id: int, memo_id: int, body: str | None = None, is_enabled: bool | None = None, is_forced: bool | None = None, *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> Memo`
  — **changed** (was `update_memo(connection, user_id, memo_id, body=None, is_enabled=None, is_forced=None) -> Memo`).
- `_refresh_memo_search_rows(connection: Connection, memo_id: int, body: str, *, client_factory: LlmClientFactory, timeout_seconds: float) -> None`
  — **new**, private: the one search seam of the module and the only place a client is ever
  built here. The two keyword arguments are **required, no defaults**, so neither call site
  can silently drift onto a default. `body` is the body *as now stored*. The helper owns
  D7's blank-body decision (non-blank → open the model, ensure the vector tables, one
  `embed_texts(handle, [body])`, `write_vector`; whitespace-only → `delete_vector` alone, no
  model resolved and no embed call) and the FTS ensure that precedes it. Strict (D8): it
  catches nothing.

**Unchanged, confirmed:**

- `delete_memo(connection: Connection, user_id: int, memo_id: int) -> None` — signature
  byte-identical (dropping a vector row needs no model, so it takes neither the factory nor
  the timeout and can never answer `no_embedding_model`). Only its docstring and body gained
  the seam.
- `reorder_memos(connection, user_id, scope, scope_id, memo_ids: list[int]) -> list[Memo]` —
  **not touched at all**: not the signature, not the body, not the docstring (016's work, and
  UC-076 says it does no vector work).
- `Memo`, `to_memo`, `list_memos`, `_require_target`, `_owned`, `_owned_update`,
  `_require_memo`, `_fetch_existing`, `_reading`, `_now_text` — untouched.

**Typing choices the coder and test-coder bind to:**

- `LlmClient`, `LlmClientFactory` and `DEFAULT_EMBED_TIMEOUT_SECONDS` are imported **from
  `app.services.embedding`** (which re-exports the first two), not from
  `app.services.llm.client` / `app.services.llm_registry`. Deliberate, and the same choice
  step 003 made: it keeps this module's `app.services` imports at **exactly one**, which is
  what the narrowed guard (`test_memos_service.py:846`/`:1208`) permits. Do not "clean it up"
  into three imports. Runtime-verified: `client_factory`'s default **is** the
  `app.services.llm.client.LlmClient` class object, and `timeout_seconds`' default evaluates
  to `30.0` read off `Settings`' field — the literal `30.0` appears nowhere in `memos.py`.
- The defaults are byte-identical to `open_embedding_model`'s and to `session_index.py`'s two
  refresh functions.

**`"title"` / `"archived_at"`: still absent.** `grep -c` over the raw source of
`app/services/memos.py` returns **0** for `title`, **0** for `archived_at` and **0** for
`fastapi` (case-insensitive), docstrings and comments included, so
`test_memos_service.py:869` and `:833` still hold. The new docstrings were written around
those words on purpose.

#### `backend/app/routers/memos.py` — real edit, not a stub (this wiring *is* interface)

Two handlers gained **the same two parameters**, appended after their existing ones (all
required, so there is no default-ordering problem):

- `settings: Annotated[Settings, Depends(get_settings)]`
- `client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)]`

on `create_own_memo` (`POST /api/memos`, 201) and `update_own_memo`
(`PATCH /api/memos/{memo_id}`, 200). Each forwards them as
`client_factory=client_factory, timeout_seconds=settings.llm_request_timeout_seconds`.
Final parameter lists, verified at runtime:

- `create_own_memo(body, current_user, connection, generator, settings, client_factory) -> MemoResponse`
- `update_own_memo(memo_id, body, current_user, connection, settings, client_factory) -> MemoResponse`

Imports added: `from app.config import Settings, get_settings`; `get_llm_client_factory`
widened into the existing `from app.dependencies import ...`; and
`from app.services.llm_registry import LlmClientFactory`.

**The override keys for the test-coder:** `app.dependencies.get_llm_client_factory` and
`app.config.get_settings` — the objects `app.dependency_overrides` must be keyed on (checked:
both are the entries these routes resolve against; the factory is step 002's shared object,
so an override set for the admin router hits these routes too).

**Unchanged, confirmed:** `list_own_memos`, `reorder_own_memos` (`PUT /api/memos/order`),
`delete_own_memo` (204) and `read_own_memo_chain` keep their exact parameter lists — none of
them can need a model. Status codes (201 / 200 / 204 / 200), request bodies
(`CreateMemoRequest`, `UpdateMemoRequest`), `MemoResponse` and the "which fields were set"
forwarding logic are all untouched. `app.openapi()` was built and compared: the memo paths are
the same five, and **no new query or body parameter appears** on create or patch
(`parameters` for `POST /api/memos` is still `None`; the patch still carries only `memo_id`),
so the two dependencies are invisible on the wire.

Structural constraints re-checked by AST over the new source: the only call to a name in
`{select, update, insert, delete}` is the pre-existing `router.delete` decorator, and the only
`sqlalchemy` import is still `Connection` (`test_memos_router.py:1161` holds).

#### The seams — where the unimplemented behaviour sits

No behaviour was implemented, and **no guard was implemented either**: a guard such as "only
when the body differs from the stored one" would have made DoD-4 / DoD-5 / DoD-7 pass against
a stub, which is exactly the accidental green a skeleton must not create. So all three write
paths reach their seam unconditionally and raise `NotImplementedError` inside their existing
`with connection.begin():` block:

- `create_memo` — after the insert and the read-back, calls `_refresh_memo_search_rows(...)`.
- `update_memo` — after the existing `if supplied:` block, calls the same helper with the body
  as now stored. A comment names the guard the coder must add: a `body` was supplied **and**
  differs from the body of the row `_require_memo` already read (capture the stored value
  there, per `004.context.md`).
- `delete_memo` — after the `rowcount` check, a bare `raise NotImplementedError` with a
  comment naming the work (`ensure_fts_tables`, then
  `delete_vector(connection, MEMO_VEC_TABLE, memo_id)`; no model).

**Consequence to expect at the red gate:** every memo create, patch and delete now raises
`NotImplementedError`, so behavioural tests in `test_memos_embedding.py`,
`test_memos_service.py` and `test_memos_router.py` fail with that one reason, which is the
intended "unimplemented" signal. `delete_memo`'s `MemoNotFoundError` path, every structural /
AST test, and everything that only reads (`list_memos`, the chain route, `reorder_memos`) are
unaffected.

- Caller-compile edits (out of Source-files scope): **None.** `app/routers/memos.py` is the
  only caller of the two changed functions anywhere in `app/`, and it is a Source file of this
  step. Both added parameters are keyword-only **with defaults**, so no call site needed
  adapting at all.

#### Gates (from `backend/`)

- `.venv/Scripts/python -m mypy app` — `Success: no issues found in 73 source files`
- `.venv/Scripts/python -m ruff check .` — `All checks passed!`
- pytest deliberately not run (the red gate is the verifier's). **No typecheck-level fallout
  anywhere**: nothing else in `app/` calls `create_memo` / `update_memo`, and nothing imports
  the new private helper.

#### Deferred imports the coder must add to `services/memos.py`

Omitted from the skeleton because ruff F401 rejects an unused import. The module currently
adds only `from app.services.embedding import DEFAULT_EMBED_TIMEOUT_SECONDS, LlmClient,
LlmClientFactory`.

- `from app.db.search_tables import MEMO_VEC_TABLE, ensure_fts_tables, ensure_vector_tables`
  — step 001's half. `MEMO_VEC_TABLE` is imported, **never** re-typed as a string literal.
  This is `app.db`, not `app.services`, so the narrowed import guard is unaffected.
- widen the `app.services.embedding` import with `delete_vector`, `embed_texts`,
  `open_embedding_model`, `write_vector` (and `EmbeddingModelHandle` if a local is annotated).
  `app.services.embedding` must remain the **only** `app.services` module this file imports.
- nothing from `app.errors` is needed: this module catches neither failure (strict, D8), and
  `errors.py` is not touched.

### Step 005 — frozen interface (2026-10-04)

#### `backend/app/services/settle.py` — real edits to delivered symbols

Two frozen dataclasses gained one **required** field each (no default — settle and re-open
always decide the outcome, and a default would let a caller silently answer "complete"). The
field is **last**, so positional construction of the earlier fields still binds:

- `SettleResult(entry_id: int, kind: parens.Kind, buried_ids: list[int], search_coverage_incomplete: bool)`
  — **changed** (was `SettleResult(entry_id, kind, buried_ids)`).
- `ReopenResult(reopened_id: int, restored_ids: list[int], search_coverage_incomplete: bool)`
  — **changed** (was `ReopenResult(reopened_id, restored_ids)`).

Two signatures changed, each by adding **the same keyword-only pair** (024 D9) and nothing
else — positional inputs and return types untouched, so every existing positional call binds:

- `settle(connection: Connection, user_id: int, session_id: int, *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> SettleResult`
  — **changed** (was `settle(connection, user_id, session_id) -> SettleResult`).
- `reopen(connection: Connection, user_id: int, session_id: int, *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> ReopenResult`
  — **changed** (was `reopen(connection, user_id, session_id) -> ReopenResult`).

**Unchanged, confirmed:** `_require_session`, `_bump_session`, `_now_text` — signatures and
bodies byte-identical. The existing refusals still fire before any refresh and before any
client is built (`ZoneEmptyError`, `ZoneNotEmptyError`, `NothingToReopenError`,
`SessionNotFoundError`).

**Where the three names come from — deliberate, do not "clean up".** `LlmClient`,
`LlmClientFactory` and `DEFAULT_EMBED_TIMEOUT_SECONDS` are imported from
**`app.services.session_index`** (which re-exports all three; step 003 recorded that
re-export), not from `app.services.embedding` / `llm.client` / `llm_registry`. That keeps the
module's *new* `app.services` import at **exactly one module** — the one the narrowed
`test_settle_service.py:930` guard permits. Verified at runtime: `client_factory`'s default
**is** the `app.services.llm.client.LlmClient` class object and `timeout_seconds`' default
evaluates to `30.0`, read off `Settings.model_fields["llm_request_timeout_seconds"]`. The
literal `30.0` appears nowhere in `settle.py`.

Structural guards re-checked by AST / source scan on the new source: `parens` is still
imported; the only `app.services` imports are `parens`, `llm.chat` and `session_index`; no
`fastapi`; **no `delete(` or `insert(` call and no `DELETE` token anywhere in the source**
(case-insensitive) — `test_settle_service.py:930`, `:970`, `:986` all still hold.

#### `backend/app/services/messages.py` — real edits to delivered symbols

- `StreamMessage` gained `search_coverage_incomplete: bool = False` as its **thirteenth and
  last** field. **The default is the load-bearing part:** every list read, every zone write,
  `_to_message`, `insert_zone_message`, `append_assistant_message`, `services/sessions.py`'s
  opening message and `services/context.py`'s consumers all keep working unchanged and answer
  "coverage complete". Runtime-checked:
  `MessageResponse.model_validate(StreamMessage(...8 fields...), from_attributes=True)
  .search_coverage_incomplete is False`.
- `file_partner_entry(connection: Connection, generator: SnowflakeGenerator, user_id: int, session_id: int, text: str, *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> StreamMessage`
  — **changed** (was `file_partner_entry(connection, generator, user_id, session_id, text) -> StreamMessage`).
- `edit_message_text(connection: Connection, user_id: int, message_id: int, text: str, *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> StreamMessage`
  — **changed** (was `edit_message_text(connection, user_id, message_id, text) -> StreamMessage`).
- `append_message(connection, generator, user_id, session_id, text) -> StreamMessage` —
  **unchanged**, byte-identical, and it does no vector work. Its result's flag is the default
  `False`. Likewise unchanged: `tool_view`, `ToolView`, `list_entries`, `list_zone`,
  `list_discussion`, `insert_zone_message`, `append_assistant_message`,
  `append_tool_message`, `_list_session_rows`, `_to_message`, `_require_session`,
  `_bump_session`, `_reading`, `_now_text`, `_json_object`.

The same import posture as `settle.py`: the three names come from
**`app.services.session_index`** — one module, the same re-export. Source re-scanned: the
module still contains **no `\bDELETE\b`** (case-sensitive, docstrings and comments included —
`test_messages_service.py:1099` holds), no `select(...)` naming `messages` or its columns,
no new `related_to` / `kind` / `settled_at` assignment, and no occurrence of the token
`parens`.

#### `backend/app/models/stream.py` — real edits (three response models)

Each gained `search_coverage_incomplete: bool` — **required, no default**, declared last, so
the backend wire always carries it (`context.md` Wire contract). Pydantic allows a required
field after defaulted ones, and every construction site already feeds it from `StreamMessage`'s
default:

- `MessageResponse` — **changed**: now **twelve** keys, `search_coverage_incomplete` after
  `tool_args`. OpenAPI-verified: it is in `properties` and in `required`.
- `SettleResponse(entry_id, kind, buried_ids, search_coverage_incomplete)` — **changed**.
- `ReopenResponse(reopened_id, restored_ids, search_coverage_incomplete)` — **changed**.

Unchanged: `NonBlankText`, `_require_non_blank`, `EntryListResponse`, `ZoneResponse`,
`DiscussionResponse` and all five request models. The module still imports only `typing`,
`pydantic` and `app.models.ids` — neither `app.services`, `app.routers`, `app.db` nor
`fastapi` (AST-checked).

**Why required and not defaulted:** `MessageResponse` is only ever built through
`model_validate(<StreamMessage>, from_attributes=True)` (`routers/stream.py:71`,
`routers/sessions.py:160`) — both sources carry the attribute, so "always present on the wire"
is achievable without a default, and a default would hide a service that forgot to decide.
Note for the test-coder: a hand-built `MessageResponse(...)` / `SettleResponse(...)` /
`ReopenResponse(...)` must now pass the field.

#### `backend/app/routers/stream.py` — real edit, not a stub (this wiring *is* interface)

Four handlers gained **the same two parameters**, appended after their existing ones (both
required, so there is no default-ordering problem), exactly as step 004 did in
`routers/memos.py` and as `compose_zone` already does:

- `settings: Annotated[Settings, Depends(get_settings)]`
- `client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)]`

Final parameter lists, verified at runtime:

- `file_partner(session_id, body, current_user, connection, generator, settings, client_factory) -> MessageResponse`
  (`POST /api/sessions/{session_id}/entries`, 201)
- `settle_zone(session_id, current_user, connection, settings, client_factory) -> SettleResponse`
  (`POST /api/sessions/{session_id}/settle`, 200)
- `reopen_group(session_id, current_user, connection, settings, client_factory) -> ReopenResponse`
  (`POST /api/sessions/{session_id}/reopen`, 200)
- `edit_message(message_id, body, current_user, connection, settings, client_factory) -> MessageResponse`
  (`PATCH /api/messages/{message_id}`, 200)

Each forwards them as `client_factory=client_factory,
timeout_seconds=settings.llm_request_timeout_seconds`. `settle_zone` / `reopen_group` now bind
the service result to a local and hand it to the mapper (one statement became two); no other
logic moved. The two mappers are real, not stubs:

- `_settle_to_response` and `_reopen_to_response` pass
  `search_coverage_incomplete=result.search_coverage_incomplete`.
- `_message_to_response` is **unchanged** — `model_validate(..., from_attributes=True)` picks
  the field up from `StreamMessage`.

Imports added: `get_llm_client_factory` widened into the existing
`from app.dependencies import CurrentUser, require_user`; `LlmClientFactory` widened into the
existing `from app.services.llm_registry import ChatClientFactory`. `Settings` / `get_settings`
were already imported for `compose_zone`. **The only `sqlalchemy` import is still `Connection`**
and there is still no `app.db.schema` import (`test_stream_router.py:1287-1330` holds).

**Unchanged handlers, confirmed** (they answer `false` from `StreamMessage`'s default, per the
"Router note" — none was touched): `list_session_entries`, `list_session_zone`,
`append_zone_message` (`POST …/zone/messages`, the zone append), `compose_zone`,
`get_discussion`, plus `get_chat_client_factory` and `get_tool_registry`. Outside this file,
`routers/sessions.py`'s seeded-session `opening_message` also picks the default up with no
edit. **All handlers stay sync `def`** (no `async` was added anywhere).

**The override keys for the test-coder:** `app.dependencies.get_llm_client_factory` and
`app.config.get_settings` — checked to be the objects these four routes resolve against;
the factory is step 002's shared object (`routers.stream.get_llm_client_factory is
app.dependencies.get_llm_client_factory` → `True`), so an override set for the admin router
hits these routes too.

**The wire did not otherwise move.** `app.openapi()` was built: the four operations' path
`parameters` are still exactly `['session_id']` / `['session_id']` / `['session_id']` /
`['message_id']` — the two dependencies add **no** query or body parameter — and the status
codes (201 / 200 / 200 / 200), request bodies and route set are unchanged.

#### The seams — where the unimplemented behaviour sits

Four seams, each a bare `raise NotImplementedError` **inside the existing
`with connection.begin():` block** at the placement `005.context.md` pins, under a comment
that spells out the exact call to write. **No behaviour and no guard was implemented**, and in
particular **the record-row-vs-zone-row dispatch is NOT coded** — a stub that skipped the
refresh for a zone row would make DoD-6 ("zone writes do no vector work") pass vacuously. So
every one of the four paths reaches its seam unconditionally:

- `settle` / `reopen` — after `_bump_session`, as the **last** statement of the block.
- `file_partner_entry` — after the insert and the bump, before the returned value is built.
- `edit_message_text` — right after the text update and 023's cached-translation discard
  (order between the two is immaterial), **before** any branch on `state.settled_at`.

Each comment names the call verbatim:
`refresh_session_vector_degraded(connection, user_id, <session id>, client_factory=client_factory,
timeout_seconds=timeout_seconds)` → `True` means coverage **incomplete**; the degraded catch
(D8: `NoEmbeddingModelError` + `LlmUnreachableError`) lives inside that step-003 function, so
nothing here catches anything and any other exception still propagates.

The `return` / construction after each seam is **unreachable** and passes a literal
`search_coverage_incomplete=False` purely so the file typechecks; a comment says so, and the
coder replaces it with the refresh's return value. For `edit_message_text` the comment notes
that the flag reaches the returned value through
`dataclasses.replace(message, search_coverage_incomplete=...)` (smaller than giving the shared
`_to_message` a parameter).

**Consequence to expect at the red gate:** every settle, re-open, partner filing and message
edit — **including a zone-row edit** — now raises `NotImplementedError`, which is the intended
"unimplemented" signal. A zone *append*, every list read, the discussion read, compose and all
refusal paths (`ZoneEmptyError`, `ZoneNotEmptyError`, `NothingToReopenError`,
`MessageNotFoundError`, `MessageNotEditableError`, `SessionNotFoundError`) are unaffected,
because every refusal precedes its seam.

- Caller-compile edits (out of Source-files scope): **None.** `app/routers/stream.py` is the
  only caller of all four changed functions and of `SettleResult` / `ReopenResult` anywhere in
  `app/`, and it is a Source file of this step. Both added parameters are keyword-only **with
  defaults**, so no other call site needed adapting; `services/compose.py` and
  `services/sessions.py` touch only `append_message` / `insert_zone_message` / `StreamMessage`,
  all unchanged or default-covered.

#### Gates (from `backend/`)

- `.venv/Scripts/python -m mypy app` — `Success: no issues found in 73 source files`
- `.venv/Scripts/python -m ruff check .` — `All checks passed!`
- `create_app()` builds and `app.openapi()` renders — no import cycle from the new
  `settle.py` / `messages.py` → `app.services.session_index` edge.
- pytest deliberately not run (the red gate is the verifier's). **No typecheck-level fallout
  anywhere** beyond this step's four files.

#### Deferred imports the coder must add

Omitted from the skeleton because ruff F401 rejects an unused import — the signatures' defaults
already use the three names, so only the function is missing:

- `app/services/settle.py` — widen the existing
  `from app.services.session_index import DEFAULT_EMBED_TIMEOUT_SECONDS, LlmClient, LlmClientFactory`
  with `refresh_session_vector_degraded`. Nothing else: this module raises, catches and imports
  no error class, and `errors.py` is not touched.
- `app/services/messages.py` — the same widening of the same import line, plus
  `replace` added to the existing `from dataclasses import dataclass` **if** the coder takes the
  `dataclasses.replace` route in `edit_message_text`.
- `app/models/stream.py`, `app/routers/stream.py` — none; both are complete.

#### One conflict the orchestrator must resolve before the red gate

`services/messages.py` now imports `app.services.session_index`, which it must: D9's defaults
cannot be expressed without `LlmClient` and `DEFAULT_EMBED_TIMEOUT_SECONDS`, and
`refresh_session_vector_degraded` lives there. But
`test_messages_service.py:1126`
(`test_the_module_imports_no_fastapi_no_service_and_no_parens__S012_002_DoD13`) fails **any**
`app.services*` import (`_FORBIDDEN_IMPORT_ROOT = "app.services"`), and the 2026-10-04 user
decision above narrowed only **three** guards — `test_memos_service.py:846`/`:1208` and
`test_settle_service.py:930`. **`messages.py`'s guard was not in that list.** The conflict is
intrinsic to the plan, not to a skeleton choice, and it is a test-side fix, so nothing was
blocked: both gates are green. `test_messages_service.py` **is** one of step 005's Test files,
so the narrowing fits the same approved pattern (permit only `app.services.session_index`;
every other `app.services` import stays an offender, and the `fastapi` / `parens` halves keep
biting) — but it needs the same explicit decision the other three got.

### Step 006 — frozen interface (2026-10-04)

#### `backend/app/services/characters.py` — real edit to a delivered function

- `update_character(connection: Connection, user_id: int, character_id: int, name: str | None = None, sheet: str | None = None, *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> Character`
  — **changed** (was `update_character(connection, user_id, character_id, name=None, sheet=None) -> Character`).
  The positional inputs, their defaults and the `Character` result are byte-identical; the
  only change is the appended keyword-only pair (024 D9), so every existing positional call
  still binds.
- **Unchanged, confirmed byte-identical:** `create_character(connection, generator, user_id, name, sheet) -> Character`,
  `archive_character(connection, user_id, character_id) -> Character`,
  `restore_character(connection, user_id, character_id) -> Character`,
  `list_characters`, `get_character`, the `Character` dataclass and every private helper
  (`_character_select`, `_to_character`, `_owned_update`, `_require_character`,
  `_fetch_existing`, `_reading`, `_now_text`). No new symbol was added to this module — the
  fan-out lives in `session_index`, so no private helper was needed.

#### `backend/app/services/setups.py` — real edit to a delivered function

- `update_setup(connection: Connection, user_id: int, setup_id: int, name: str | None = None, description: str | None = None, *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> Setup`
  — **changed** (was `update_setup(connection, user_id, setup_id, name=None, description=None) -> Setup`).
  Same shape, same reasoning.
- **Unchanged, confirmed byte-identical:** `create_setup(connection, generator, user_id, character_id, name, description) -> Setup`,
  `archive_setup(connection, user_id, setup_id) -> Setup`,
  `restore_setup(connection, user_id, setup_id) -> Setup`, `list_setups`, `get_setup`, the
  `Setup` dataclass and every private helper, `_require_parent_character` included. No new
  symbol.

**Typing choices both downstream roles bind to.** `LlmClient`, `LlmClientFactory` and
`DEFAULT_EMBED_TIMEOUT_SECONDS` are imported **from `app.services.session_index`** (which
re-exports them from `app.services.embedding`), exactly as step 005 did in `settle.py` and
`messages.py`. That keeps each module's `app.services` imports at **exactly one —
`app.services.session_index`** — which is precisely the import the user's 2026-10-04
narrowing authorised for these two files. Do not "clean it up" into two or three imports.
Runtime-verified for both functions: `client_factory`'s default **is** the
`app.services.llm.client.LlmClient` class object, and `timeout_seconds`' default evaluates to
`30.0` read off `Settings`' field — the literal `30.0` appears in neither module.

#### The source-scan guards these two modules must keep passing — re-verified after the edit

- **`grep -ci delete` over `app/services/characters.py` → 0, and over `app/services/setups.py`
  → 0.** The substring does not occur anywhere in either file, comments and docstrings
  included, so `test_characters_service.py:446-457` and `test_setups_service.py:625-660`
  (`"delete(" not in source.lower()` plus the `\bdelete\b` IGNORECASE regex) still hold. Every
  added docstring and comment was written around the word on purpose; the fan-out reaches
  `delete_vector` only indirectly, through `session_index`, which is a different file.
- **An AST import walk over `app/services/setups.py`** lists exactly `collections.abc`,
  `contextlib`, `dataclasses`, `datetime`, `typing`, `sqlalchemy`, `app.db.schema`,
  `app.errors`, `app.ids`, `app.services.session_index` — **nothing from
  `app.services.characters`** (nor any submodule), so `_FORBIDDEN_IMPORT` finds no offender.
  The substring `app.services.characters` does not occur in the source text either (0 hits).
- **`grep -ci fastapi` → 0** in both modules, so both `_FASTAPI_IMPORT` scans still pass.

#### `backend/app/routers/characters.py` — real edit, not a stub (this wiring *is* interface)

`update_own_character` (`PATCH /api/characters/{character_id}`, 200) gained two parameters,
appended after its existing ones:

- `settings: Annotated[Settings, Depends(get_settings)]`
- `client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)]`

and forwards them as `client_factory=client_factory,
timeout_seconds=settings.llm_request_timeout_seconds`. Final parameter list, verified at
runtime: `update_own_character(character_id, body, current_user, connection, settings,
client_factory) -> CharacterResponse`.

Imports added: `from app.config import Settings, get_settings`; `get_llm_client_factory`
widened into the existing `from app.dependencies import ...`; and
`from app.services.llm_registry import LlmClientFactory`.

**Unchanged, confirmed:** `list_own_characters`, `create_own_character` (201),
`read_own_character`, `archive_own_character`, `restore_own_character` keep their exact
parameter lists — none of them can need a model. Status codes, request models, `_to_response`
and the router's `dependencies=[Depends(require_user)]` are untouched, and no route was added
or removed.

#### `backend/app/routers/setups.py` — real edit, not a stub

`update_own_setup` (`PATCH /api/setups/{setup_id}`, 200) gained **the same two parameters** in
the same position and forwards them the same way. Final parameter list, verified at runtime:
`update_own_setup(setup_id, body, current_user, connection, settings, client_factory) ->
SetupResponse`. The same three imports were added.

**Unchanged, confirmed:** `list_own_setups`, `create_own_setup` (201), `read_own_setup`,
`archive_own_setup`, `restore_own_setup`, both path families, and the no-prefix router
declaration.

#### The override keys for the test-coder

`app.dependencies.get_llm_client_factory` and `app.config.get_settings` — the **same two
objects** step 004 wired into `routers/memos.py` and step 005 into `routers/stream.py`
(checked by identity: `typing.get_type_hints(..., include_extras=True)` on both new handlers
resolves `Depends(...).dependency is app.dependencies.get_llm_client_factory` → `True` and
`... is app.config.get_settings` → `True`; and `app.routers.admin_llm.get_llm_client_factory
is app.dependencies.get_llm_client_factory` → `True`). So one
`app.dependency_overrides[get_llm_client_factory] = lambda: fake` reaches these two PATCH
routes as well.

**Invisible on the wire, verified.** `app.openapi()` was built and read: the character /
setup paths are still the same ten, and `PATCH /api/characters/{character_id}` and
`PATCH /api/setups/{setup_id}` each still declare exactly one parameter, their path id. The
two dependencies add no query or body parameter.

#### The seams — where the unimplemented behaviour sits

Per the step's instruction and step 004's / 005's precedent, **no behaviour and no dispatch
condition was written.** Writing "only when the sheet / description differs from the stored
one" would have let the no-op clauses of DoD-3, DoD-4 and DoD-6 pass against a stub, which is
exactly the accidental green a skeleton must not create. So each `update_*` reaches its seam
**unconditionally** and raises:

- `update_character` — `raise NotImplementedError` as the **last statement of the existing
  `with connection.begin():` block**, after the `if supplied:` write (`006.context.md`
  Placement: the fan-out runs after the update so the composed texts read the new value).
- `update_setup` — the same, in its own `with` block.

A comment at each seam names, in order, the work the coder fills in: (1) the dispatch
condition, diffing against the stored value **captured at the `_require_character` /
`_require_setup` read that already runs before the update** (never re-read after it);
(2) `session_ids_for_character(connection, user_id, character_id)` /
`session_ids_for_setup(connection, user_id, setup_id)`, ascending id, archived sessions
included, no archive predicate (U4); (3) only when that list is non-empty (N > 0),
`refresh_session_vectors(connection, user_id, session_ids, client_factory=client_factory,
timeout_seconds=timeout_seconds)` — with N == 0 skipped, or called with an empty collection,
either way resolving no model; and the strict posture (D8): nothing is caught, so the
transaction rolls back and the edit is not stored.

**Consequence to expect at the red gate:** every `update_character` and `update_setup` call
now raises `NotImplementedError`, which is the intended "unimplemented" signal. That covers
the PATCH routes of both routers. Everything else is unaffected — the creates, archive,
restore, every read, and every structural / AST test in the four listed test files, because
`create_character` and `create_setup` were not touched at all. Per harvest F4, no existing
test changes a `sheet` or `description` on a character or setup **that has sessions**, so
under the N > 0 rule the only existing failures are this `NotImplementedError`, never a
missing designated model.

- Caller-compile edits (out of Source-files scope): **None.** `app/routers/characters.py` and
  `app/routers/setups.py` are the only callers of the two changed functions anywhere in
  `app/` (`services/configuration.py`'s `update_character_configuration` is a different
  symbol and was not touched), and both routers are Source files of this step. Both added
  parameters are keyword-only **with defaults**, so no call site needed adapting at all.

#### Gates (from `backend/`)

- `.venv/Scripts/python -m mypy app` — `Success: no issues found in 73 source files`
- `.venv/Scripts/python -m ruff check .` — `All checks passed!`
- pytest deliberately not run (the red gate is the verifier's). **No typecheck-level fallout
  anywhere.**

#### Deferred imports the coder must add

Omitted from the skeleton because ruff F401 rejects an unused import. Each module currently
adds only `from app.services.session_index import DEFAULT_EMBED_TIMEOUT_SECONDS, LlmClient,
LlmClientFactory`.

- `app/services/characters.py` — widen that one import with `refresh_session_vectors` and
  `session_ids_for_character`. **Nothing else.** No `app.db.search_tables` import (the module
  writes no vector row itself and must never name a vector table), nothing from `app.errors`
  (strict: it catches neither failure, and `errors.py` is not touched), and **no second
  `app.services` import** — `app.services.session_index` must stay the only one.
- `app/services/setups.py` — the same, with `refresh_session_vectors` and
  `session_ids_for_setup`.
- Both routers are complete: they need no further import.

### Step 007 — frozen interface (2026-10-04)

Three Source files, all under `frontend/src/app/`. Gate: `npm run typecheck` (from
`frontend/`) — **clean**, both projects. `npm test` deliberately not run (the red gate is the
verifier's).

#### `frontend/src/app/streamApi.ts` — three types widened, no function touched

- `Message` — **changed**: gains `search_coverage_incomplete?: boolean` as its twelfth key,
  after `tool_args`. Was the eleven-key type.
- `SettleResult` — **changed**: `{ entry_id: string; kind: MessageKind; buried_ids: string[];
  search_coverage_incomplete?: boolean }`. Was the three-key type.
- `ReopenResult` — **changed**: `{ reopened_id: string; restored_ids: string[];
  search_coverage_incomplete?: boolean }`. Was the two-key type.
- The field is **optional on all three** (D10) and **absent reads as `false`**. It is never
  `boolean | undefined` in a required position, so every existing full-`Message` builder
  (023's included) and every `toEqual({…})` on a stubbed `SettleResult` / `ReopenResult` still
  typechecks and still passes.
- **Unchanged, byte-identical:** `MessageRole`, `MessageKind`, `ToolStatus`, the three private
  response types, `sessionPath`, and all seven calls — `fetchEntries`, `fetchZone`,
  `filePartnerEntry`, `appendZoneMessage`, `settleZone`, `reopenLastEntry`, `composeZone`,
  `fetchDiscussion`, `editMessage`. No new export.

#### `frontend/src/app/streamState.ts` — one observable field, four captured results

- **The field, frozen name: `searchCoverageIncomplete`** —
  `StreamState.searchCoverageIncomplete: boolean`, declared `= false`, the last field before
  the constructor. It is a plain observable (`makeAutoObservable`'s only exclusion stays
  `composeHandle`), so `new StreamState(sessionId)` still yields `false` on a fresh mount
  (D11, U5). The class still holds **data only** — no method, no getter, no computed. Tests
  read it as `state.searchCoverageIncomplete`.
- The type import widened to `import type { Message, ReopenResult, SettleResult } from
  "./streamApi";` — the two result types are now named in the effect bodies.
- **Signatures unchanged, all five:** `sendComposer(state, signal?) -> Promise<void>`,
  `filePastedPartner(state, text, signal?) -> Promise<void>`,
  `settleComposer(state, signal?) -> Promise<void>`,
  `reopenLast(state, signal?) -> Promise<void>`,
  `editEntry(state, messageId, text, signal?) -> Promise<boolean>`. No export added or
  removed anywhere in the module.

**The result capture — the real change harvest A3 called for, and the shape the coder fills.**
Four of the five effects discarded their result; each now captures it into a `let` declared
before the `try`, left `undefined` when the request failed:

| Effect | Captured variable | Type |
|---|---|---|
| `sendComposer` (partner branch) | `filed` | `Message \| undefined` |
| `filePastedPartner` | `filed` | `Message \| undefined` |
| `settleComposer` | `settled` | `SettleResult \| undefined` |
| `reopenLast` | `reopened` | `ReopenResult \| undefined` |
| `editEntry` | `updated` (already existed) | `Message` |

- In `sendComposer` the old `let sent = false` / `sent = true` flag is **gone**: its one reader
  became `if (filed !== undefined) { clearDraftIfUnchanged(state, text); }`. Same condition,
  same behaviour — the request either resolved or it did not.
- **The seam.** Each effect carries a `// SEAM — 024 step 007 (D10, D11), unimplemented`
  comment at the exact point the flag write belongs, followed by `void <captured>;` so the
  capture compiles under `noUnusedLocals`. **The coder replaces that `void` statement with the
  `runInAction` write** — `state.searchCoverageIncomplete = <result>.search_coverage_incomplete
  ?? false` — and nothing else. Placement, per effect:
  - `settleComposer`, `reopenLast` — after the request's `try`/`catch` and the
    `if (signal?.aborted) return;`, **before** the `rereadBoth`, guarded on the captured value
    being defined.
  - `sendComposer` (partner), `filePastedPartner` — the same position, guarded additionally on
    `filed.settled_at !== null`, because a zone row must leave the flag unchanged.
  - `editEntry` — **inside the existing `runInAction` at the settled path only**. Its
    `updated.settled_at === null` early return (`rereadBoth`) is left exactly as it was and is
    already D11-correct: a row re-opened elsewhere writes no flag.
- **No flag write belongs in any `catch`** (D11: a failed request leaves the flag as it is),
  and none is stubbed there. `editZoneMessage` is untouched — the zone-row edit is out of this
  step.
- No seam **throws**. These five effects are delivered behaviour whose existing contract is
  "never rejects"; a throwing stub would break tests in files this step does not own. The
  consequence the red gate must expect: **the flag stays `false` through every effect**, so
  DoD-1..4's "sets it true" halves fail (true red), while the clauses whose expectation *is*
  `false` / "unchanged" (DoD-2's absent case, DoD-5, DoD-7, DoD-6's flag-false half) pass
  against the stub. That is inherent to a field the contract requires to start `false`.

#### `frontend/src/app/SessionStream.tsx` — the banner, declared inline

- **Rendered inline in `SessionStream`'s ready branch. No new component, no new export, no new
  prop** — `SessionStreamProps` is byte-identical (`sessionId`, `sendBlockedReason?`). The
  component stays an `observer`, so the flag flipping re-renders it.
- Position: the **first child of the `<Stack gap="md">`**, immediately before
  `<StreamRecord state={state} … />`, therefore before the first record entry in document
  order. 023's `TranslationState` / `disposeTranslations` lines are preserved untouched.
- Declaration, exactly as frozen:

  ```tsx
  {state.searchCoverageIncomplete ? (
    <Alert role="alert" color="yellow">
      {COVERAGE_BANNER_TEXT}
    </Alert>
  ) : null}
  ```

- `const COVERAGE_BANNER_TEXT` is a module-level constant (mirroring `RULER_LABEL`), **not
  exported**, holding the sentence pinned by `007.context.md` verbatim:
  `"Search coverage is incomplete. Your latest change was saved, but it could not be indexed for search."`
  The test-coder asserts that string, which comes from the plan, not from this module.
- `role="alert"` is passed explicitly. Mantine 7's `Alert` already hardcodes `role: "alert"`
  after spreading `...others` (verified in `node_modules/@mantine/core/cjs/.../Alert.cjs`), so
  the accessible role is `alert` either way; the explicit prop documents the contract and
  survives a Mantine change. `getByRole("alert")` is the binding.
- **No close button** (`withCloseButton` is not passed; Mantine's default is false), no
  `title`, no `icon`. It disables nothing: the record, the editors, `KindSwitch`, `ZoneList`
  and `Composer` render exactly as before, with the same props.
- Import added: `Alert` widened into the existing
  `import { Alert, Box, Button, Center, Divider, Loader, Stack, Text } from "@mantine/core";`.
  Nothing else was imported, and no notification API is imported anywhere in the three files
  (`tests/conventions.test.ts` still holds).

#### DoD-6 / DoD-7 mechanism — the decision `007.context.md` left to the skeleton

**The test must drive a stubbed settle through the UI. There is no seam to pre-set the flag,
and none was invented.** `StreamState` is created in `useState` inside `SessionStream` (L35);
it is not a prop, not exported, not in a ref or context, and `SessionStream.tsx` /
`StreamRecord.tsx` expose no `data-testid`. The banner is inline, so **it is not independently
unit-testable** as a component (unlike `StreamRecord` / `KindSwitch` / `ZoneList`, which take
`state` as a prop). Consequences for `SessionStreamCoverage.test.tsx`:

- **DoD-6** — render `<AppProviders><SessionStream sessionId={…} /></AppProviders>`, stub the
  stream load, press the existing settle control, and answer `POST
  /api/sessions/<id>/settle` with `search_coverage_incomplete: true`; then assert
  `getByRole("alert")`'s text, that it precedes the first record entry in document order, and
  that the entry's edit affordance is present and enabled. The flag-false half is the same
  flow with `false` (or a mount with no write).
- **DoD-7** — a fresh mount with a successful stream load and no write: assert no
  `role="alert"` node.

#### The `written(state)` snapshot helper — checked, and it does not break (harvest C9's gap)

Both copies enumerate three fields explicitly and nothing else:

```ts
function written(state: StreamState) {
  return { entries: toJS(state.entries), zone: toJS(state.zone), draft: state.draft };
}
```

(`tests/app/streamMutations.test.ts:737`, `tests/app/entryEffects.test.ts:357`). It does **not**
enumerate state fields generically, so the new observable never enters those snapshots and the
four `expect(written(state)).toEqual(before)` assertions
(`streamMutations.test.ts:766,798`, `entryEffects.test.ts:383,419`) are unaffected.

#### Fallout and caller edits

- **`npm run typecheck` is clean, and there is no test-file fallout** — expected, because the
  new type field is optional and the new class field is additive. `tsconfig.json` includes
  `tests/`, so a type break in any existing test file would have surfaced here; none did.
- The convention scans were re-checked by grep over the three changed files: no
  `@mantine/notifications` import, and no `parseInt`, `Number.parseInt` or `id: number`-shaped
  text on any line, comments included (`tests/ids-are-strings.test.ts` scans raw lines).
- Caller-compile edits (out of Source-files scope): **None.** Every change is additive — an
  optional type key, one new class field, four local captures and one conditional element —
  so no caller anywhere in `src/` or `tests/` needed adapting.

#### Deferred import the coder must add

- `frontend/src/app/streamState.ts` — none. `runInAction` is already imported, and
  `ReopenResult` / `SettleResult` are already in the type import and already used. The coder
  adds **no import** to any of the three files.

### Step 008 — frozen interface (2026-10-04)

Four Source files: one new module under `frontend/src/shared/`, three existing state modules
under `frontend/src/app/`. Gate: `npm run typecheck` (from `frontend/`) — **clean**, both
projects. `npm test` deliberately not run (the red gate is the verifier's).

**Binding correction carried from `## Ultra phase` (3):** the character surface is
**`commitPersona`**, not `submitSave` — there is no `submitSave` in `characterScreenState.ts`.
DoD-4 is to be read as "`commitPersona` … follows the same three cases".

#### `frontend/src/shared/embeddingFailure.ts` — new module, fully implemented

- `frontend/src/shared/embeddingFailure.ts` — `embeddingFailureSentence(error: unknown): string | null` — **new**.
  Pure, total, no state, no notification API, no React, no MobX. Implemented in full (DoD-1
  pins it exactly, and there is no seam worth leaving in a three-branch mapping). It returns
  null for anything that is not an `ApiError` (`isApiError` from `./apiError`) and for every
  `ApiError` code other than the two below. The parameter is named `error` and typed `unknown`;
  **status is never inspected** — only `code` — so the 409 / 502 pairing is the backend's
  business and the helper answers the same sentence whatever the status.
- Two **exported module constants**, frozen names and exact text (`008.context.md`, verbatim —
  tests compare against these, never a retyped copy):
  - `NO_EMBEDDING_MODEL_SENTENCE` = `"Not saved: no embedding model is configured, so this text can't be indexed for search. Ask your administrator to set one."`
  - `LLM_UNREACHABLE_SENTENCE` = `"Not saved: the embedding server could not be reached. Try again in a moment."`
- Two **non-exported** code constants, `NO_EMBEDDING_MODEL_CODE = "no_embedding_model"` and
  `LLM_UNREACHABLE_CODE = "llm_unreachable"`. `ApiError.code` is a plain `string` and there is
  no code registry (harvest B6), so the comparison is a string compare. Tests must not import
  these two; they construct `new ApiError(code, message, status, detail?)` with the literals.
- Conventions held: no `@mantine/notifications` import (`tests/conventions.test.ts`), and the
  raw-line scans of `tests/ids-are-strings.test.ts` (`parseInt`, `Number.parseInt`,
  `\w*(id|Id)\s*\??\s*:\s*number`) find nothing, comments included — grep-verified.
- Import is relative (`./apiError`). No other import.

#### The four effects — channel and current generic sentence (what the test-coder binds to)

Required by `008.context.md`: the test-coder never reads the source, so DoD-2..5 bind to this
table. Every signature below is **unchanged**, and so is every other behaviour of all four.

| Effect | Module | Signature (unchanged) | Channel the sentence lands in | Read in a test as | Current generic sentence (unchanged fallback) |
|---|---|---|---|---|---|
| `saveNote` (save path) | `src/app/memoLevelState.ts` | `saveNote(state: MemoLevelState, memoId: string): Promise<void>` | the observable map `MemoLevelState.failures: Record<string, string>`, keyed by memo id, **replaced not mutated** | the pure accessor `noteFailure(state, memoId): string \| null` | `"Could not save the note."` |
| `saveNewNote` | `src/app/memoLevelState.ts` | `saveNewNote(state: MemoLevelState): Promise<void>` | `MemoLevelState.newNote: MemoNewNote \| null`, field `failure`; the object is **replaced**, keeping the typed text | `state.newNote?.failure` | `"Could not save the note."` |
| `commitPersona` | `src/app/characterScreenState.ts` | `commitPersona(state: CharacterScreenState, characters: CharactersState): Promise<void>` | the observable `CharacterScreenState.error: string \| null` | `state.error` | `"Could not save the character."` |
| `submitSetup` | `src/app/setupDraft.ts` | `submitSetup(draft: SetupDraft, onSaved: (saved: Setup) => void, signal?: AbortSignal): Promise<void>` | the observable `SetupDraft.error: string \| null` | `draft.error` | `"Could not create the setup."` when `draft.original === null`, else `"Could not save the setup."` — chosen **before** the request |

- **None of the four calls `notifyFailure`** (harvest B6/B8). Every one surfaces through an
  observable field, so `embeddingFailureSurfacing.test.ts` needs no notification mock and the
  expected `notifyFailure` call count stays zero everywhere.
- Routes to stub (harvest B8): `PATCH /api/memos/<id>` with `{body}`; `POST /api/memos` with
  `{scope, scope_id, body}`; `PATCH /api/characters/<id>` with `{sheet}`;
  `POST /api/characters/<characterId>/setups` with `{name, description}` and
  `PATCH /api/setups/<setupId>` with `{name, description}`. Ids are percent-encoded by the api
  modules.
- **Deliberately untouched, and out of DoD-2..5:** `saveNote`'s blank-text branch (it DELETEs
  and writes `"Could not delete the note."`), the flag-toggle PATCH
  (`"Could not change the note."`), the reorder (`"Could not reorder the notes."` →
  `state.reorderFailureText`), `commitName` and `submitCreate` on the character screen
  (`"Could not save the character."` / `"Could not create the character."`). D5 embeds only a
  **changed `sheet`**, a **changed `description`** and a memo **body** create or edit, so none
  of those paths can receive `no_embedding_model` or `llm_unreachable`.

#### The interface change in the three state modules — exactly what moved

- **No signature changed, no export added or removed, no field added**, in any of the three.
  The classes still hold data only (pure-data-contract memory note). Each module's sole change
  is inside one existing `catch`.
- **`catch {` → `catch (error)`** in three places — this is the interface change (harvest: these
  three did not bind the caught value and so could not inspect a code):
  - `memoLevelState.ts` `saveNote`, the **PATCH** catch only (the blank-path DELETE catch stays
    a bare `catch {`);
  - `memoLevelState.ts` `saveNewNote`;
  - `characterScreenState.ts` `commitPersona`.

  `setupDraft.ts` `submitSetup` already bound `error` (its abort guard reads it); it is
  unchanged in that respect.
- **Deferred import the coder must add:**
  `import { embeddingFailureSentence } from "../shared/embeddingFailure";` in **each of the
  three** `src/app/` modules. It is **not** added by the skeleton: `tsconfig.json` sets
  `noUnusedLocals`, so an unused import would fail the gate. No other import changes anywhere.

#### The seam shape, and its red-gate consequence

Each of the four catches now reads (names and comment marker identical in all four):

```ts
// SEAM — 024 step 008 (D8), unimplemented. … The coder replaces `null` below with
// `embeddingFailureSentence(error)` …
void error;                        // omitted in setupDraft.ts, which already reads `error`
const refusal: string | null = null;
runInAction(() => { /* …existing write… */ refusal ?? <EXISTING GENERIC SENTENCE> });
```

- **`void error;`** is present in the three catches whose binding is otherwise unread, so the
  new binding compiles under `noUnusedLocals` and reads as deliberate. The coder deletes that
  line when it fills the seam.
- **Only the code-specific override is unimplemented.** `refusal` is a `string | null` local
  pinned to `null`, and the `?? <generic>` fallback preserves today's behaviour
  byte-for-byte. **The seam does not throw** — these four effects' delivered contract is "never
  rejects", and a throwing stub would break tests in five files this step does not own
  (`memoLevelState.test.ts`, `characterScreenState.test.ts`, `setupDraft.test.ts`,
  `MemoLevelGroup.test.tsx`, `CharacterScreen.test.tsx` all assert the exact generic sentences).
  **The coder's whole job is the one-expression substitution per catch:** replace `null` with
  `embeddingFailureSentence(error)`, drop the `void error;`, add the import.
- **Red-gate consequence, stated so the verifier expects it:**
  - DoD-1 (`embeddingFailure.test.ts`) **passes in full** against the skeleton — the helper and
    both constants are delivered, by design.
  - DoD-2..5: the **third case of each** (a 500 with another code surfaces the pre-existing
    generic sentence, unchanged) **passes**, because the fallback is the delivered behaviour, and
    harvest C10 confirms no existing test stubs these two codes, so nothing is displaced.
  - DoD-2..5: the **`no_embedding_model` and `llm_unreachable` halves fail** — each surfaces the
    generic sentence instead of the pinned one. That is the true red: four effects × two codes =
    eight failing assertions, each failing with "received the generic sentence", never with a
    throw, a timeout or a type error.

#### Fallout and caller edits

- Caller-compile edits (out of Source-files scope): **None.** Nothing in `src/` or `tests/`
  calls the changed internals, no signature moved and no field was added, so no call site
  needed adapting. `tsconfig.json` includes `tests/`, so a break in any existing test file would
  have surfaced in `npm run typecheck`; none did.

## Tests

### Step 001 — tests (2026-10-04)

- `backend/tests/test_search_tables.py` (new) — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5,
  DoD-6, DoD-7, DoD-9, DoD-10 — the FTS/vec0 ensure observed only through `MATCH`,
  `integrity-check`, point lookups and `sqlite_master`.
- `backend/tests/test_bootstrap_service.py` (amended) — **gained DoD-8 only**; every
  existing test, helper and assertion is unchanged (one new test plus the four table-name
  constants added to the import block).

Test inventory (all names end `__S024_001_DoD<n>`):

| DoD | Test(s) | Asserts |
|---|---|---|
| 1 | `test_ensure_creates_both_full_text_tables`, `test_a_second_ensure_changes_no_catalogue_entry_and_no_indexed_content` | both tables present after a committed ensure; a second call raises nothing and leaves the identical `sqlite_master` (tables **and** triggers) set and the identical per-token `MATCH` content on both tables |
| 2 | `test_backfill_indexes_every_existing_memo`, `test_backfill_indexes_the_record_row`, `test_backfill_leaves_zone_and_buried_rows_unindexed` (parametrized: zone, buried), `test_backfill_leaves_both_indexes_sound` | back-fill from pre-existing rows: each memo token → its id as rowid; the record row's token → its id; the zone and buried tokens → **nothing** (so `message_fts` cannot have used `'rebuild'`); `integrity-check` on both tables |
| 3 | `test_memo_insert_update_and_delete_follow_the_index`, `test_a_flag_or_order_only_memo_update_leaves_every_match_unchanged` (parametrized: `is_enabled`, `is_forced`, `sort_key`) | insert indexed; body edit moves the index off the old token onto the new; a flag-only / `sort_key`-only update leaves **every** `MATCH` result unchanged; delete un-indexes; `integrity-check` after the sequence |
| 4 | `test_message_triggers_cover_every_state_transition` | the ordered (a)–(g) sequence on one row plus two extra rows: zone insert and zone edit not found; **case (c) one settle-shaped UPDATE setting `settled_at` and rewriting `text` together** → new text found, pre-settle text not; record-row text edit swaps old for new; re-open-shaped clearing of `settled_at` un-indexes; a born-settled row found; a `related_to`-set row not; `integrity-check` on **both** tables after **every** step |
| 5 | `test_vector_ensure_creates_both_tables_at_the_given_dimension`, `test_a_second_same_dimension_vector_ensure_preserves_an_existing_row`, `test_a_different_dimension_is_refused_as_no_embedding_model`, `test_a_refused_dimension_leaves_both_tables_at_the_original_one` | `ensure_vector_tables(conn, 8)` creates both and each reports 8; a second 8 call preserves a previously inserted vector row; a 16 call raises `NoEmbeddingModelError` with `code == "no_embedding_model"` and `detail == {"reason": "dimension_mismatch"}` plus a non-empty fixed message; both tables still report 8 afterwards |
| 6 | `test_dimension_is_none_when_the_vector_table_was_never_created` (parametrized: `memo_vec`, `session_vec`) | the read-back is `None` for each name on a `create_all`-only database |
| 7 | `test_a_rolled_back_transaction_leaves_no_virtual_table_and_no_trigger` | both ensures inside one rolled-back transaction leave none of the four tables, no shadow table of theirs, and **no trigger at all** |
| 8 | `test_creation_ensures_the_full_text_tables_only` (in `test_bootstrap_service.py`) | `create_first_administrator` on an empty database leaves `memo_fts` / `message_fts` present and `memo_vec` / `session_vec` absent |
| 9 | `test_snowflake_ids_are_the_full_text_rowids`, `test_a_vector_under_a_snowflake_id_round_trips` (parametrized: `memo_vec`, `session_vec`) | a memo and a message with ids above 2^60 are indexed by the triggers with FTS rowid **equal to the id**; a point lookup by such an id returns a vector whose deserialised values equal the inserted ones |
| 10 | `test_no_virtual_or_shadow_table_is_registered_in_the_metadata` | none of the four names, and no name prefixed by one of them (every FTS5 / vec0 shadow table), is a key of `schema.metadata.tables` |

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
DoD-9 ✓, DoD-10 ✓. No `[manual/live]` item in this step.

Notes for the verifier:

- **DoD-10 is green before implementation by its nature** — it is a pure negative structural
  assertion over `schema.metadata.tables` (D2) and calls none of the three functions. It
  binds to the frozen interface by importing the four constants; it guards a regression the
  coder could introduce, so a pass at the red gate is expected, not a tautology fault.
- Conventions held: `conftest.py` untouched; the only fixture is the **file-local** `engine`
  (registry + two users, a character and a session each); every `memos` / `messages` id is
  above 2^60; no monkeypatching; the tables are observed only from the test side.
- Per `001.context.md`, `test_bootstrap_router.py` and `test_db_schema.py` are deliberately
  unlisted — a red-gate failure in either is a `SPEC` hand-back, not a test fault here.

### Step 002 — tests (2026-10-04)

- `backend/tests/llm_fakes.py` (new) — **the shared provider fake**, no tests of its own.
  Steps 003–006 import it. Public contract below.
- `backend/tests/test_embedding_service.py` (new) — covers DoD-1, DoD-2, DoD-3, DoD-4,
  DoD-5, DoD-6, DoD-7, DoD-8, DoD-10 — the designated-model handle, the sync bridge, the two
  failure codes and the vector-row forms, observed only from the test side.
- `backend/tests/test_dependencies.py` (amended) — **gained DoD-9 only**; two new tests
  appended at the end plus five import lines. Every pre-existing test, fixture, helper and
  assertion is byte-identical, and the module docstring gained one additive paragraph.
- `backend/tests/test_admin_llm_router.py` — **not edited, deliberately** (DoD-11). Its
  import line is `from app.routers.admin_llm import get_llm_client_factory` (L37) and the
  skeleton verified the name is still re-exported there as the identical object, so both
  `dependency_overrides` fixtures (L361, L385) key the entry the routes resolve against. The
  move breaks nothing about how the file imports the dependency, so no edit was warranted.

#### `backend/tests/llm_fakes.py` — the public contract steps 003–006 bind to

Bind to this record; there is no need to read step 002's tests.

| Symbol | Contract |
|---|---|
| `FAKE_EMBEDDING_DIM = 8` | the dimension 024's tests designate |
| `embedding_vector(text: str, dim: int) -> list[float]` | **pure**; same `(text, dim)` → same list; **different texts → different vectors**; `len(...) == dim`; every component is a multiple of `2**-8` in `[-0.5, 0.49609375]`, so it is **exactly float32-representable** and a round-trip through `sqlite_vec.serialize_float32` / `struct.unpack` compares **equal with no tolerance**. This is how a test computes the vector it expects to find stored for a composed text (D6 / D7). |
| `vectors_for(texts, dim) -> list[list[float]]` | `[embedding_vector(t, dim) for t in texts]` — the expected answer of one `embed_texts(handle, texts)`, in input order |
| `FakeEmbeddingClient` | satisfies `LlmClientLike` (`probe` + `embed`). `dim`; `embed_calls: list[tuple[str, tuple[str, ...]]]` records **every** call as `(model_name, tuple(texts))` in call order; `probe_calls: int`; scripted `error: Exception \| None` (raised **after** the call is recorded) and `returned_length: int \| None` (vectors of that length instead of `dim`) |
| `FakeClientFactory` | callable `(base_url, api_key, timeout_seconds) -> FakeEmbeddingClient`, matching `LlmClientFactory`. `calls: list[tuple[str, str \| None, float]]` per construction; **`call_count: int`** — `factory.call_count == 0` is the direct assertion for "this write did **no vector work**", which D5's no-vector-work clauses use throughout the feature; `clients: list[FakeEmbeddingClient]`; `embed_calls` concatenates every client's, so `factory.embed_calls == [(MODEL, ("a", "b"))]` asserts "**exactly one** call carrying these texts **in this order**" (D1); `probe_calls` |
| `fake_factory(dim=FAKE_EMBEDDING_DIM)` | the happy path |
| `wrong_length_factory(dim=..., returned_length=...)` | vectors of the wrong length → the service must answer `no_embedding_model` / `{"reason": "dimension_mismatch"}` (D8) |
| `unreachable_factory(dim=..., reason=...)` | `embed` raises `LlmUnreachableError("…", {"reason": reason})`, also exposed as `factory.error`; `reason` defaults to `ProbeOutcome.UNREACHABLE.value` |

No network, no event loop of its own, **no monkeypatching**: every user injects through the
frozen `client_factory=` keyword seam.

#### Test inventory (all names end `__S024_002_DoD<n>`)

| DoD | Test(s) | Asserts |
|---|---|---|
| 1 | `test_open_returns_the_designated_name_and_dimension`, `test_open_builds_exactly_one_client_with_url_resolved_key_and_timeout`, `test_open_makes_no_outbound_call`, `test_the_default_timeout_is_the_settings_field_default` | the handle carries `MODEL_NAME` and `8`; `factory.call_count == 1` and `factory.calls == [(BASE_URL, RESOLVED_KEY, 12.5)]` — the **variable's value** (the env var is really set and resolved) and the **passed** timeout; `handle.client is factory.clients[0]`; no `embed` and no `probe`; omitting `timeout_seconds` passes `DEFAULT_EMBED_TIMEOUT_SECONDS`, whose expected value is read from `Settings.model_fields["llm_request_timeout_seconds"].default` — the literal `30.0` appears nowhere in the test file |
| 2 | `test_an_unusable_designation_is_no_embedding_model_and_builds_nothing` (parametrized: `no_designation`, `designated_but_disabled`), `test_an_empty_registry_is_no_embedding_model_and_builds_nothing` | `NoEmbeddingModelError` with `code == "no_embedding_model"`, and `factory.call_count == 0` in every case — the refusal precedes construction (R4, no substitution) |
| 3 | `test_an_unset_key_variable_raises_secret_ref_missing_and_builds_nothing` | an `api_key_ref` of `"$S024_002_ABSENT_VARIABLE"` raises `app.errors.SecretRefError` with `code == "secret_ref_missing"`, and `factory.call_count == 0` |
| 4 | `test_embed_texts_answers_one_vector_per_text_in_input_order`, `test_embed_texts_makes_exactly_one_call_carrying_the_batch_in_order`, `test_embed_texts_accepts_a_tuple_and_a_single_text` | three texts → `vectors_for(TEXTS, 8)` exactly, each of length 8, and three **distinct** vectors (a broadcast single vector would fail); `factory.embed_calls == [(MODEL_NAME, tuple(TEXTS))]` — one call, the model name, the batch in order; a one-element `tuple` binds too |
| 5 | `test_a_wrong_length_vector_is_a_dimension_mismatch` (parametrized: 7, 9), `test_a_single_wrong_length_vector_in_the_batch_is_enough` | `NoEmbeddingModelError` with `code == "no_embedding_model"` and `detail` **exactly** `{"reason": "dimension_mismatch"}` (D8) |
| 6 | `test_an_unreachable_provider_propagates_unchanged`, `test_an_auth_failure_also_propagates_as_llm_unreachable` | `type(exc) is LlmUnreachableError`, `code == "llm_unreachable"`, `detail` unchanged (`{"reason": "unreachable"}` / `{"reason": "auth_failed"}`), and **not** a `NoEmbeddingModelError` |
| 7 | `test_embed_texts_runs_from_plain_synchronous_code`, `test_embed_texts_runs_on_a_worker_thread_with_no_event_loop` | the sync bridge answers `vectors_for(TEXTS, 8)` from plain sync test code, **and** from a `threading.Thread` with no event loop (the thread finishes, raised nothing, and recorded exactly one `embed` call) |
| 8 | `test_writing_twice_leaves_one_row_holding_the_second_vector`, `test_a_written_vector_is_serialised_as_float32`, `test_writing_two_ids_keeps_them_apart`, `test_delete_removes_the_row`, `test_deleting_an_absent_id_raises_nothing`, `test_deleting_when_the_table_was_never_created_raises_nothing` — **each parametrized over `MEMO_VEC_TABLE` and `SESSION_VEC_TABLE`** | on tables made by `001`'s `ensure_vector_tables(conn, 8)` with ids above 2^60: two writes of one id leave `count(*) == 1` holding the **second** vector; the blob is byte-identical to `sqlite_vec.serialize_float32(v)` (D4); a second id is untouched; delete removes that row only; deleting an absent id raises nothing and changes nothing; **deleting on a `create_all`-only database where the table was never created raises nothing and creates nothing** — the tolerance step 003 relies on |
| 9 | `test_the_shared_llm_client_factory_answers_the_real_client`, `test_the_admin_router_exposes_the_very_same_factory_object` (both in `test_dependencies.py`) | `app.dependencies.get_llm_client_factory()` **is** the real `LlmClient` class; `app.routers.admin_llm.get_llm_client_factory` **is** `app.dependencies.get_llm_client_factory`; and an override keyed on the admin router's name leaves `dependency_overrides` with that one shared key (D9) |
| 10 | `test_the_module_imports_no_fastapi`, `test_the_module_binds_no_fastapi_symbol` | an AST import walk over `app.services.embedding`'s source finds no `fastapi` / `starlette` import (the `test_bootstrap_service.py:529-548` idiom), and no module-level name is a `fastapi` / `starlette` object |
| 11 | the **existing, unedited** suites in `backend/tests/test_admin_llm_router.py` and `backend/tests/test_dependencies.py` | regression fallout: both pass unchanged. No new test was written and no assertion was altered — per the step text, those files are edited only if the move breaks how they import the dependency, and it does not |

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
DoD-9 ✓, DoD-10 ✓, DoD-11 ✓ (existing suites, unedited). No `[manual/live]` item in this step.

Notes for the verifier:

- **DoD-9 and DoD-11 are green before `embedding.py` is implemented, by their nature.** They
  assert the dependency move, which the skeleton already performed as a real edit (not a
  stub), so a pass at the red gate is expected and is not a tautology. Everything in
  `test_embedding_service.py` calls a stubbed function and must fail with
  `NotImplementedError`, except DoD-10's two structural tests, which call none of them and
  guard a regression the coder could introduce.
- Conventions held: `conftest.py` untouched; the only fixtures are the **file-local**
  `engine` (`create_all` only) and `key_present` (`monkeypatch.setenv` of a non-`RPHELPER_`
  name, harvest F7); **no module attribute is patched anywhere**; registry rows are raw
  inserts; every id is above 2^60; the vector tables are read only through
  `pragma_table_info` (the key column is discovered, never re-typed) and point lookups.
- The timeout `12.5` is deliberately unequal to `Settings`' declared default, so DoD-1's
  "the passed timeout" is distinguishable from "the default".
- Listed-file discipline: no file outside this step's four Test files was touched.

### Step 003 — tests (2026-10-04)

- `backend/tests/test_session_index.py` (new) — covers DoD-1 … DoD-12 — the D6 composition
  pinned exactly, owner scope, the one-client-one-call strict refresh, the three
  "unavailable" conditions in both postures, the empty-text and N = 0 rules, the fan-out id
  sets and the FTS ensure, observed only from the test side.
- No other file was touched: `conftest.py`, every step file, `context.md` and `outcome.md`
  are unchanged, and no existing test file needed amending (this step adds no field to any
  response model and changes no delivered signature).

Test inventory (all names end `__S024_003_DoD<n>`):

| DoD | Test(s) | Asserts |
|---|---|---|
| 1 | `test_the_session_text_is_persona_setup_then_settled_entries` | the five seeded rows (settled "Alpha", buried "Buried", settled "Beta", settled decision "((Gamma))", zone "Draft") compose to **exactly** `"Persona P.\n\nSetup S.\n\nAlpha\n\nBeta\n\n((Gamma))"`, the step file's literal — one equality proving persona-first order, the `"\n\n"` join, the `settled_entries` boundary and ascending-id order; plus explicit "Buried"/"Draft" absent, "((Gamma))" present (US-115, US-122.AC-2) |
| 2 | `test_a_session_with_no_setup_composes_without_a_setup_part`, `test_an_empty_sheet_and_no_setup_composes_from_the_entries_alone`, `test_a_whitespace_only_settled_entry_contributes_no_part` | `setup_id` null → `"Persona P.\n\nAlpha"`; empty `sheet` and no setup → `"Alpha\n\nBeta"`; a whitespace-only settled entry → `"Persona P.\n\nAlpha\n\nBeta"` with no doubled separator (D6) |
| 3 | `test_another_users_session_composes_to_the_empty_string`, `test_a_strict_refresh_of_another_users_session_writes_no_row` | user B composing A's session gets `""`; a strict refresh by B on a database whose `session_vec` exists leaves **no row for that id**, `count(*) == 0`, and `factory.call_count == 0` (R5, D6) |
| 4 | `test_three_sessions_are_refreshed_in_one_embed_call` | three sessions, designation at dim 8: three rows, each equal to `embedding_vector(<its own composed text>, 8)`; `factory.call_count == 1`; **exactly one** `embed` call, with `MODEL_NAME` and the three composed texts (compared order-insensitively — the plan pins the batch, not its order). A per-session loop fails this (D1) |
| 5 | `test_no_designated_model_is_refused_and_leaves_the_row_alone`, `test_an_unreachable_provider_propagates_and_leaves_the_row_alone`, `test_a_table_at_another_dimension_is_a_dimension_mismatch` | each condition raises from `refresh_session_vectors` (`code` `no_embedding_model` / `llm_unreachable`, the third with `detail` **exactly** `{"reason": "dimension_mismatch"}`), and the pre-existing `session_vec` row is byte-for-byte unchanged afterwards — the third against a table declared at **16** while the designation says **8** (D8) |
| 6 | `test_a_degraded_refresh_without_a_model_commits_the_row_and_keeps_the_stale_vector`, `test_a_degraded_refresh_with_an_unreachable_provider_commits_the_row`, `test_a_degraded_refresh_with_a_dimension_mismatch_commits_the_row`, `test_a_wrong_length_vector_also_degrades_and_keeps_the_row` | in each condition: **raises nothing**, returns `True`, a real `sessions.last_used_at` UPDATE made earlier **in the same transaction** is committed (`== BUMPED_AT`), and the row still holds V (stale, U5). The fourth is D8's other mismatch raise site (a wrong-length returned vector), degrading identically (US-112.AC-1) |
| 7 | `test_a_degraded_success_answers_complete_and_rewrites_the_vector` | returns `False`, the row equals `embedding_vector(<current composed text>, 8)` (replacing the pre-existing V), and there is exactly one row (D5, D4) |
| 8 | `test_an_empty_text_degraded_refresh_is_complete_and_drops_the_row`, `test_an_empty_text_strict_refresh_raises_nothing_and_drops_the_row` | empty sheet + no setup + no settled entry (only a zone row) composes to `""`; the degraded refresh with **no** model returns `False` (complete, not degraded) and the pre-existing row is **gone**; the strict refresh raises nothing and also drops it; `factory.call_count == 0` in both (D6) |
| 9 | `test_an_empty_id_collection_needs_no_model` | `refresh_session_vectors(conn, A, [], ...)` with no designation raises nothing, `factory.call_count == 0`, `factory.embed_calls == []` (U4) |
| 10 | `test_every_session_of_a_character_is_listed_archived_included`, `test_only_the_sessions_using_a_setup_are_listed_archived_included`, `test_another_users_character_and_setup_fan_out_to_nothing` | `set(session_ids_for_character(A, C)) == {S1, S2, S3, S4}` with S2 **archived** and included (U4, no archive predicate); `set(session_ids_for_setup(A, X)) == {S1, S2}`; both empty for user B against A's character / setup (R5). Results are wrapped in `set(...)` — the frozen return is an ascending `list[int]` |
| 11 | `test_a_degraded_refresh_ensures_and_backfills_the_message_index` | on a `create_all`-only database (`message_fts` asserted **absent** first), a degraded refresh with no model leaves `message_fts` present and back-filled: a `MATCH` on the settled entry's nonsense token returns exactly that message's id (D2) |
| 12 | `test_the_module_imports_no_fastapi`, `test_the_module_binds_no_fastapi_symbol` | an AST import walk over `app.services.session_index`'s source finds no `fastapi` / `starlette` import (the `test_bootstrap_service.py:529-548` idiom, as step 002 used), and no module-level name is a `fastapi` / `starlette` object |

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓. No `[manual/live]` item in this step.

Notes for the verifier:

- **DoD-12's two tests are green before implementation by their nature** — they are pure
  negative structural assertions over the module's AST and namespace, call none of the five
  functions, and guard a regression the coder could introduce. Not a tautology fault.
- Everything else calls a frozen function and must fail "unimplemented". Several tests also
  set up through `001`'s `ensure_vector_tables` and `002`'s `write_vector`, so at the red gate
  they fail with `NotImplementedError` raised during setup rather than at the call under test
  — that is the stub signal, not a binding error.
- **DoD-4's embed-call texts are compared order-insensitively on purpose.** The plan pins
  "one call carrying the three composed texts" and never pins which order a `Collection`
  iterates, so asserting a tuple order would assert more than the spec requires.
- Conventions held: `conftest.py` untouched; the only fixtures are the file-local `engine`
  (registry + two users + three characters + three setups, `create_all` only so no virtual
  table pre-exists) and `fanout` (DoD-10's five sessions); sessions and messages are
  raw-inserted per test; every id is above 2^60; **no monkeypatching** — the designation is
  raw `llm_servers` / `models` rows with a **null `api_key_ref`** (so no secret has to
  resolve) and the client arrives through the frozen `client_factory=` seam from
  `tests/llm_fakes.py`; `messages.kind` is left null everywhere, because D6 composes the
  `text` column alone and no kind vocabulary needed inventing.
- The vector tables are observed only through `pragma_table_info` (the key column is
  discovered, never re-typed), point lookups and `struct.unpack`; `message_fts` only through
  `MATCH`. 024 issues no query of its own.

### Step 004 — tests (2026-10-04)

- `backend/tests/test_memos_embedding.py` (new) — covers DoD-1 … DoD-9 — the strict embed on
  create and on a changed body, the two failure codes with a full rollback, the four
  no-vector-work paths (flag-only, body equal to stored, blank body, reorder), the delete, and
  the four router wire cases. Observed only from the test side.
- `backend/tests/test_memos_service.py` (amended) — the **guard narrowing** (approved
  deviation, below) plus the **regression repair** (DoD-10). No memo assertion was changed,
  loosened or removed.
- `backend/tests/test_memos_router.py` (amended) — the **regression repair** only (DoD-10). No
  assertion, route, status code or wire key changed.
- `backend/tests/test_memos_models.py` — deliberately **not** touched (`004.context.md`: out of
  scope). No other file was touched: `conftest.py`, every step file, `context.md` and
  `outcome.md` are unchanged.

Test inventory (all new names end `__S024_004_DoD<n>`):

| DoD | Test(s) | Asserts |
|---|---|---|
| 1 | `test_a_create_embeds_the_body_alone_and_indexes_it` | with a designation at dim 8, `create_memo` with `"The innkeeper is Kaelith."` returns the memo; the `memo_vec` row **equals** `embedding_vector(body, 8)`; `factory.embed_calls == [(MODEL_NAME, (body,))]` and `call_count == 1` (one client, one call, the body as the whole batch — D1 / D7); a `memo_fts` `MATCH` on `"Kaelith"` returns exactly that id (UC-042, US-119, D5) |
| 2 | `test_a_create_with_no_designated_model_stores_nothing`, `test_a_create_with_an_unreachable_provider_stores_nothing` | `NoEmbeddingModelError` (`code == "no_embedding_model"`) with no designation, and `LlmUnreachableError` (`code == "llm_unreachable"`) from a scripted fake; in **both** cases afterwards: **no `memos` row with that body, zero `memo_vec` rows and no `memo_fts` hit** — the whole transaction rolled back, DDL included (D8, `backend-structure.md`) |
| 3 | `test_a_changed_body_replaces_the_vector`, `test_a_changed_body_without_a_model_changes_nothing` | a body edit rewrites `memo_vec` to `embedding_vector(<new body>, 8)` with exactly one embed call of the new body and one row remaining; with the designation withdrawn the same call raises `no_embedding_model` and **both** the stored body and the stored blob are byte-identical to before (UC-043, US-104) |
| 4 | `test_a_flag_only_update_needs_no_model_at_all` (parametrized: `is_enabled`, `is_forced`, both), `test_a_flag_only_update_does_no_vector_work` | with **no** designation each flag-only update succeeds and persists both flags (and leaves the body alone); then with a designation **and** a dedicated recording factory the same three calls make **`call_count == 0`**, `embed_calls == []`, and the memo's `memo_vec` blob is **byte-identical** before and after (UC-044, UC-075, D5) |
| 5 | `test_a_body_equal_to_the_stored_one_does_no_vector_work` | `body` equal to the stored body plus `is_forced=True`: succeeds with **no** model designated, the flag persists, and the factory records **zero** constructions and zero embed calls (D5) |
| 6 | `test_a_delete_drops_the_row_its_vector_and_its_index_entry` | a memo that has a vector is deleted with the designation **withdrawn**: the `memos` row, its `memo_vec` row (and the table's whole row count) and its `memo_fts` hit are all gone (D5) |
| 7 | `test_a_whitespace_only_create_has_no_vector`, `test_an_update_to_a_blank_body_removes_the_vector` | a whitespace-only create succeeds with **no** model designated, zero factory calls and no `memo_vec` row; and a later update to a blank body on a memo that **had** a vector removes the row, again with zero factory calls and no designation in place — D7's "no model is resolved and no embed call is made", which the frozen `_refresh_memo_search_rows` record also pins |
| 8 | `test_a_reorder_does_no_vector_work` | three memos created through the one recording factory (so three real `memo_vec` rows), then `reorder_memos` (016) returns the new order while `factory.calls` and `factory.embed_calls` are **unchanged** and **every** `memo_vec` row is byte-identical (UC-076, D5). `reorder_memos` takes no factory — it is not modified — so "zero factory calls" is measured as "the one factory in play records nothing further across the reorder", which is noted in the test docstring |
| 9 | `test_a_create_without_a_model_answers_409_and_lists_nothing`, `test_a_create_with_a_designated_model_answers_201`, `test_a_body_patch_with_an_unreachable_provider_answers_502`, `test_a_flag_only_patch_answers_200_without_a_model` | through `create_app()` with `dependency_overrides` on the two keys the skeleton recorded (`app.dependencies.get_llm_client_factory`, `app.config.get_settings`): `POST /api/memos` → 409 `{"error": {...}}` with `code == "no_embedding_model"` and the level's list empty; with a designation → **201** with exactly the nine `Memo` wire keys, the stored vector right, and the factory built once with `settings.llm_request_timeout_seconds`; a body `PATCH` against a raising fake → **502** `llm_unreachable` with the stored body unchanged; a `PATCH` carrying only `is_enabled` with **no** model → **200**, flag persisted, `call_count == 0` (D8, Wire contract) |
| 10 | the **amended** existing suites in `test_memos_service.py` and `test_memos_router.py` | regression fallout: both pass again once given the precondition. No new test; see the repair below |

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
DoD-10 ✓ (existing suites, amended). No `[manual/live]` item in this step.

#### Approved deviation — the two import guards, narrowed (user decision, 2026-10-04)

Recorded under `## Ultra phase` → conflict (1), and implemented here verbatim.
`test_memos_service.py:846` (`..._imports_no_other_service__S015_002_DoD15`) and `:1208`
(`..._still_has_no_fastapi_and_no_service_import__S016_001_DoD14`) failed **any**
`from app.services…` / `import app.services…`, which step 004's Interface intent requires
`app/services/memos.py` to have. Both tests keep their names and their `__S015_002_DoD15` /
`__S016_001_DoD14` suffixes; the AST walks now share one predicate,
`_is_forbidden_service_import`, built on a single new constant:

```python
_PERMITTED_SERVICE_IMPORT = "app.services.embedding"
```

**Only that one named module is permitted** (exact match — not a prefix). Every other
`app.services` module, and every relative import, stays an offender, so the invariant still
bites: adding `app.services.characters` to `memos.py` still fails both tests. One permitted
import suffices because the skeleton re-exports `LlmClient`, `LlmClientFactory` and
`DEFAULT_EMBED_TIMEOUT_SECONDS` **through** `app.services.embedding`. `:869`'s
`"title"` / `"archived_at"` substring guard and `:833`'s no-`fastapi` guard are **untouched**.

#### The regression repair (DoD-10) — fixtures, not call sites

D5 makes memo create and memo body edit require a designated embedding model, so the ~27
`_create(` sites and the body-edit sites in `test_memos_service.py` and **all 25** tests of
`test_memos_router.py` (harvest F3) needed a precondition. It was supplied in the **shared
fixtures and wrappers**, not at the call sites — four places in total, covering every affected
test at once:

- `test_memos_service.py`: the `engine` fixture now also calls a new
  `_seed_embedding_designation` (one `llm_servers` row + one enabled, `is_embedding_designated`
  `models` row, `embedding_dim` 8, null `api_key_ref`); the `_create` and `_update` wrappers
  gained an optional `factory` parameter and pass `client_factory=` (a fresh
  `fake_factory(FAKE_EMBEDDING_DIM)` by default) through the frozen keyword seam. `_delete` is
  unchanged — `delete_memo` needs no model. No existing call site was edited, and no call site
  passes a fourth positional argument.
- `test_memos_router.py`: `_seed` now also calls the same new `_seed_embedding_designation`,
  and the `application` fixture adds
  `app.dependency_overrides[get_llm_client_factory] = lambda: embedding_factory` (a new
  file-local `embedding_factory` fixture returning the shared fake) **alongside** the existing
  `get_settings` override. No test body was edited.

Both files gained only a docstring paragraph recording this; **no assertion about memo
behaviour was changed, loosened or deleted** in either. Refused paths (foreign / unknown
target, blank body → 422, an already-deleted memo, a nothing-supplied update) never reach the
embed path, so they needed nothing; the factory they now receive is simply never used.

Notes for the verifier:

- Per `004.context.md`, a red-gate failure in **any existing test file other than
  `test_memos_service.py` / `test_memos_router.py`** is a `SPEC` hand-back, not a test fault
  here. `test_memos_models.py` is explicitly out of scope and untouched.
- Expect the stub signal (`NotImplementedError`) from every create, patch and delete — the
  skeleton record states all three write paths reach their seam unconditionally, with no guard
  implemented. That includes the DoD-4 / DoD-5 / DoD-7 / DoD-8 setup creates, so several of
  those tests fail during setup rather than at the call under test; that is the stub signal, not
  a binding error. The two narrowed guard tests and `:869` / `:833` are structural and pass at
  the red gate by their nature.
- Conventions held: `conftest.py` untouched; no source file read or written; the only fixtures
  in the new file are the file-local `engine`, `generator` and the routers' established autouse
  `configure_logging` neutralisation; every id in the new file is above 2^60; the designation is
  raw `llm_servers` / `models` rows with a **null `api_key_ref`** so no secret resolves (no
  `monkeypatch.setenv` was needed at all); the client always arrives through the frozen
  `client_factory=` seam or the shared dependency override; `memo_vec` is read only through
  `pragma_table_info`, point lookups and `struct.unpack`, and `memo_fts` only through `MATCH`.
- DoD-1's `embed_calls` is compared as an exact one-element list — unlike step 003's DoD-4, the
  batch here is a single text, so order is not at issue.

### Step 005 — tests (2026-10-04)

- `backend/tests/test_record_keeping_embedding.py` (new) — covers DoD-1 … DoD-8 — the degraded
  `session_vec` refresh on settle, re-open, the settled-row edit and partner filing; the two
  "unavailable" conditions; the zone no-vector-work dispatch; and the coverage flag on the wire.
  Observed only from the test side.
- `backend/tests/test_settle_service.py` (amended) — the **guard narrowing** (approved deviation
  A, below). No behavioural assertion changed: no `SettleResult` / `ReopenResult` is compared as
  a whole object anywhere in the file.
- `backend/tests/test_messages_service.py` (amended) — the **guard narrowing** (approved deviation
  A). No behavioural assertion changed: `StreamMessage`'s new field defaults to `False`, so both
  `StreamMessage(...)` comparisons and every list read still hold.
- `backend/tests/test_stream_models.py` (amended) — the **key-set repair** (deviation B) plus
  DoD-8's "each response model declares the boolean field" clause.
- `backend/tests/test_stream_router.py` (amended) — the **key-set / exact-body repair** only.
- `backend/tests/test_sessions_router.py`, `backend/tests/test_discussion_read.py`,
  `backend/tests/test_tool_rows.py`, `backend/tests/test_tool_wire_fields.py` (amended) — their
  `MessageResponse` key sets **only** (approved deviation C, the orchestrator's four-file scope
  extension). Nothing else in those four was touched.
- `backend/tests/test_sessions_models.py` (amended) — its embedded-`MessageResponse` key set
  **only** (deviation B's sixth row; the orchestrator's fifth-file scope extension, `## Ultra
  phase` conflict (5)). Nothing else in the file was touched.
- Not touched: `conftest.py`, every step file, `context.md`, `outcome.md`, and every existing test
  file outside the ten above.

Test inventory (all new names end `__S024_005_DoD<n>`):

| DoD | Test(s) | Asserts |
|---|---|---|
| 1 | `test_a_settle_with_a_model_embeds_the_post_settle_text` | with a designation at dim 8 and an assistant candidate `"Hello there."`: flag **false**, the zone empty, the record `[head]`; the `session_vec` row **equals** `embedding_vector(<D6 text ending with the head's text as now stored>, 8)` — the stored text is **read back after the settle**, so a refresh placed before the settle's UPDATE fails this (the clause proving the refresh is the block's last statement); `factory.call_count == 1`, `factory.embed_calls == [(MODEL_NAME, (text,))]`; a `message_fts` `MATCH` on `"there"` returns exactly that id (D5, D6, R11) |
| 2 | `test_a_settle_without_a_model_still_settles_and_flags_coverage`, `test_a_settle_without_a_model_leaves_a_stale_vector_byte_identical`, `test_a_settle_with_an_unreachable_provider_has_the_same_outcome` | US-112.AC-1 / D8 / U5: with **no** designation the settle raises nothing — the entry is settled (visible through `settled_entries`), the zone is empty — the flag is **true**, and either no `session_vec` row exists at all (`count(*) == 0` on a database where the table was never created) or a pre-existing one is **byte-identical** to the blob written before. With a designation and a fake raising `LlmUnreachableError` the outcome is the same, and the client was really built (`call_count == 1`, D1) |
| 3 | `test_a_reopen_with_a_model_embeds_a_text_without_the_reopened_entry`, `test_a_reopen_without_a_model_still_reopens_and_flags_coverage` | with a model: flag **false**, `reopened_id` / `restored_ids` as before, and the row equals `embedding_vector(<the surviving entry's text alone>, 8)`, with the re-opened row's **stored text asserted absent** from what was embedded (the re-open's own fresh factory records exactly that one call). With no model: `reopen` succeeds, the flag is **true**, the group is back in the zone and the earlier entry is still recorded (R11, D5) |
| 4 | `test_a_settled_edit_with_a_model_embeds_the_new_text` — **parametrized over `turn`, `decision`, `partner`** | US-110.AC-2 / US-109.AC-2 / UC-078: editing a settled record row of each kind from `"Old words"` to `"New words"` returns flag **false** and stores the new text; the row equals `embedding_vector(<D6 text containing "New words">, 8)`; the single embed call's text contains `"New words"` and **not** `"Old words"` |
| 5 | `test_a_settled_edit_without_a_model_still_saves_and_flags_coverage` | US-112.AC-1 / US-112.AC-2 / U5: the edit **saves** — the stored text and the returned message both `"New words"` — the flag is **true**, and the pre-existing `session_vec` blob is byte-identical (stale) with exactly one row |
| 6 | `test_a_zone_append_does_no_vector_work`, `test_a_zone_row_edit_does_no_vector_work` | US-115 / D5 / Wire contract: with a designation in place and a recording factory, a zone append and a zone-row edit each answer flag **false**, record `call_count == 0` and `embed_calls == []`, and leave the `session_vec` blob byte-identical. The zone edit is the real dispatch proof — it receives the factory through the frozen seam and must still build nothing, while the same call on a settled row embeds (DoD-4). `append_message` takes no factory (frozen, unchanged), which the test docstring states |
| 7 | `test_partner_filing_with_a_model_embeds_the_filed_text`, `test_partner_filing_without_a_model_still_files_and_flags_coverage` | with a model: flag **false**, the row equals the vector of the D6 text, and the single embed call's text **contains the filed text**. With no model: the entry is still filed — born settled, `kind == "partner"`, in the record, the zone empty — and the flag is **true** (US-121.AC-1 unchanged, US-112.AC-1) |
| 8 | `test_settle_answers_the_coverage_flag_true_without_a_model`, `test_reopen_answers_…_true_…`, `test_a_settled_row_patch_answers_…_true_…`, `test_partner_filing_answers_…_true_…`, `test_a_zone_append_answers_the_coverage_flag_false`, `test_settle_answers_the_coverage_flag_false_with_a_model` (all in the new file) + `test_each_record_keeping_response_declares_the_coverage_flag`, `test_the_coverage_flag_is_always_on_the_wire`, `test_each_record_keeping_response_serialises_the_flag_as_a_json_boolean` (in `test_stream_models.py`) | through `create_app()` with `dependency_overrides` on the two keys the skeleton recorded (`app.dependencies.get_llm_client_factory`, `app.config.get_settings`): with no designation, settle → 200 `{entry_id, kind, buried_ids, search_coverage_incomplete: true}` as an **exact body**, re-open → 200 `true`, `PATCH /api/messages/{id}` on a settled row → 200 `true`, `POST /api/sessions/{id}/entries` → **201** `true`, and a **zone append → `false`**; with a designation and the fake factory the same settle answers an exact body with **`false`**, built one client with `settings.llm_request_timeout_seconds` (D9). Plus: all three response models declare `search_coverage_incomplete`, annotated `bool`, and it is in `properties` **and** `required` of each JSON schema, serialising as a JSON boolean both ways (US-112.AC-2, Wire contract) |
| 9 | the **amended** existing suites in `test_stream_models.py`, `test_stream_router.py`, `test_settle_service.py`, `test_messages_service.py` and the four extended files | regression fallout: each passes again with the new key accepted. No new test; see the repair below. `entry_id`, `kind`, `buried_ids`, `reopened_id`, `restored_ids` and every message field are unchanged |

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
DoD-9 ✓ (existing suites, amended). No `[manual/live]` item in this step.

**Verify-run repair (2026-10-04) — DoD-9, `backend/tests/test_messages_service.py`.** Two
assertions were wrong, not the implementation. Both compared a record-keeping write's returned
`StreamMessage` against a list-read `StreamMessage` as whole dataclass objects, and the two
values now differ on the new field by design: the file designates no embedding model, so under
**D8** every write there answers `search_coverage_incomplete = True` (DoD-5, DoD-7) while a list
read answers the field's `False` default (005's Interface intent, the feature Wire contract).

- `test_a_filed_partner_block_is_in_the_entries_and_not_the_zone__S012_002_DoD3`:
  `assert filed in entries` → `assert _message_fields(filed) in [_message_fields(entry) for entry
  in entries]`.
- `test_the_edited_turn_stays_at_its_position_in_the_entries_not_the_zone__S014_001_DoD1`:
  `assert entries[1] == edited` → `assert _message_fields(entries[1]) == _message_fields(edited)`.

Form chosen: a new file-local helper `_message_fields`, `replace(value,
search_coverage_incomplete=False)`, which leaves the one new field out of the whole-object
equality and keeps the other twelve (`id`, `session_id`, `role`, `kind`, `text`, the three
instants, `related_to`, the tool columns) in it. Both tests are about **position and
zone-absence**, so a row that moved, changed text or landed in the wrong list still fails them —
neither was weakened, and no other assertion, test name or guard in the file changed (the import
`from dataclasses import replace` and the 024 paragraph of the module docstring are the only other
edits). The narrower repair was correct because the alternative — designating a model on the
file's `engine` fixture and threading a fake through `client_factory=` — would have switched every
record-keeping write in all 64 tests onto the model-present path, exercising different behaviour
than the file's 012/014 clauses are about; DoD-9 asks only that these suites pass again "with the
field accepted", with their other message-field assertions unchanged. The flag's own values on
both paths remain pinned in `test_record_keeping_embedding.py`.

#### Approved deviation A — two import guards, narrowed (the user's 2026-10-04 principle)

Both keep their test names and their `__S012_…` suffixes, and each permits **exactly one** named
module (an exact match, never a prefix), so every other `app.services` module stays an offender.

- **`test_settle_service.py:930`** (`test_settle_imports_parens_and_no_other_service__S012_003_DoD23__S021_001_DoD10`)
  — recorded under `## Ultra phase` conflict (1), the user's decision of 2026-10-04. A new constant
  `_ALLOWED_INDEX_MODULE = "app.services.session_index"` adds one branch beside the existing
  `_ALLOWED_CHAT_MODULE` one. `parens` **is** still asserted imported, `strip_think` is still the
  only name allowed from `app.services.llm.chat`, and `:970` (no `fastapi`) and `:986` (no
  `delete(` / `insert(` / `DELETE`) are **untouched**.
- **`test_messages_service.py:1126`** (`test_the_module_imports_no_fastapi_no_service_and_no_parens__S012_002_DoD13`)
  — recorded under `## Ultra phase` conflict (4): the orchestrator applying the same user principle
  to the fourth guard of the same kind, in a file that is already one of step 005's declared Test
  files. A new constant `_PERMITTED_SERVICE_IMPORT = "app.services.session_index"` and one shared
  predicate `_is_forbidden_service_import` replace the two inline `_FORBIDDEN_IMPORT_ROOT` checks.
  The `fastapi` and `parens` halves still bite, and `messages.py`'s other guards are **untouched**:
  `:1082` (no `select(...)` naming `messages`), `:1099` (the `translations`-only delete rule, the
  alias check and the `\bDELETE\b` scan), `:1157` (`related_to`) and `:1495` (`kind` / `settled_at`
  / `related_to` in `.values()`).

#### Approved deviation B — the `MessageResponse` key-set repair, file by file

`search_coverage_incomplete` is **required** on the three response models (skeleton record), so
harvest F2's exact-key and exact-equality pins each gained the one key and nothing else:

| File | What changed |
|---|---|
| `test_stream_models.py` | `MESSAGE_WIRE_KEYS` (`:51`, used by `:241` and the two listing tests) gained the key; `_message()`'s default values gained `search_coverage_incomplete: False` (the model is required, so every hand-built response must pass it); the two `SettleResponse` constructions and their expected dicts (`:293`, `:303`) and the two `ReopenResponse` ones (`:312`, `:318`) gained `False` on both sides |
| `test_stream_router.py` | `MESSAGE_KEYS` (`:70`, used by `_assert_message_shape` at `:334`) gained the key; the two `SettleResponse` exact bodies (`:450`, `:505`) gained `"search_coverage_incomplete": True` and the `ReopenResponse` exact body (`:758`) gained `False` — see the note below |
| `test_sessions_router.py` | `MESSAGE_KEYS` (`:84`, used by `_assert_message_wire_shape` at `:1022`) |
| `test_discussion_read.py` | `MESSAGE_KEYS` (`:102`, used at `:469`) |
| `test_tool_rows.py` | `MESSAGE_KEYS_022` (`:484`, derived from `:72`, used at `:531`) — the 012 eight-key constant at `:72` is left as the historical record |
| `test_tool_wire_fields.py` | `MESSAGE_KEYS` (`:63`, used at `:472`, `:492`, `:523`) |
| `test_sessions_models.py` | **Added by `## Ultra phase` conflict (5)** (red gate run 1 — 018's `StartedSessionResponse.opening_message` embeds `MessageResponse`). `MESSAGE_WIRE_KEYS` (`:442`, used by the two `__S018_001_DoD6__S022_001_DoD4` tests) gained the key → **twelve**; `_message_value()` gained `search_coverage_incomplete=False` (required field, and the opening message is a zone row, which the Wire contract pins to `false`); `EXPECTED_MESSAGE_WIRE` gained `"search_coverage_incomplete": False`. Nothing else: the session-side `WIRE_KEYS`, `EXPECTED_SESSION_WIRE` and every other assertion are untouched, and both tests still pin an **exact** key set and an exact wire object |

**The true/false choice in `test_stream_router.py` is derived from the plan, not from the code.**
That file designates no embedding model, so the degraded path (D8) answers **`true`** wherever the
session text is non-empty — the two settles at `:450` / `:505`, whose sessions hold settled entries
— and **`false`** at `:758`, where the re-open empties the record and `_new_session` gives the
character a blank `sheet` and no setup, which by **D6** makes the session text empty: nothing to
embed, no model resolved, the outcome complete. A comment at each site states the reasoning. For
the same reason the new file's DoD-8 re-open case settles an earlier entry that **survives** the
re-open, so that its session text stays non-empty and the clause's `true` is reachable.

#### Approved deviation C — four files added to this step's Test files

`test_sessions_router.py`, `test_discussion_read.py`, `test_tool_rows.py` and
`test_tool_wire_fields.py` are **not** listed in `005.record-keeping-paths.md`. The orchestrator
extended step 005's Test files by exactly those four, for their `MessageResponse` key-set
assertions only, under this feature's regression-fallout protocol — recorded under `## Ultra
phase` conflict (2) (harvest F2: `MessageResponse` is pinned to exactly eleven keys in seven
files). Nothing else in the four was touched: no behavioural assertion, no fixture, no model
seeding (none of them needs a designation — their writes are a zone append and a zone-row edit,
which do no vector work, and their other routes only read).

Notes for the verifier:

- Per `context.md`'s regression-fallout protocol and `005.context.md`, a red-gate failure in any
  existing test file **other than the ten named above** is a `SPEC` hand-back, not a test fault
  here. Deliberately unlisted and untouched, though they call the same write paths (harvest F3):
  `test_settle_tool_rows_and_think.py`, `test_translation_invalidation.py`,
  `test_assistant_append.py`, `test_zone_message_insert.py`, `test_llm_sse_harness.py`,
  `test_compose_route.py`, `test_compose_source.py`, `test_translation_router.py`. None of them
  pins a `SettleResult` / `ReopenResult` / `StreamMessage` as a whole object or a `MessageResponse`
  key set, so none is expected to fail.
- **Expect the stub signal (`NotImplementedError`) from every settle, re-open, partner filing and
  message edit — a zone-row edit included** (skeleton record: all four seams are reached
  unconditionally and the record-row-vs-zone dispatch is deliberately not coded). So DoD-6's
  zone-edit test fails at the red gate too, which is correct: a stub that skipped the refresh for
  a zone row would have made it pass vacuously. The zone *append* case, the three model-declaration
  tests and the key-set repairs are structural or default-covered and pass at the red gate by
  their nature.
- The DoD-8 wire cases will surface the seam as a 500, not as the pinned status — again the stub
  signal, not a binding error.
- Conventions held: `conftest.py` untouched; no source file was read or written; the only fixtures
  in the new file are the file-local `engine`, `generator`, `wire_engine` and the routers'
  established autouse `configure_logging` neutralisation; every id in the new file is above 2^60,
  and the three `messages` ids a settle orders are chosen so the head is the largest; the
  designation is raw `llm_servers` / `models` rows with a **null `api_key_ref`**, so no secret
  resolves and no `monkeypatch.setenv` was needed; the client always arrives through the frozen
  `client_factory=` seam or the shared dependency override; `session_vec` is read only through
  `pragma_table_info`, point lookups and `struct.unpack`, and `message_fts` only through `MATCH`.

#### Repair — 2026-10-04 (file-write corruption, tail only)

`test_record_keeping_embedding.py` failed to parse: two lines of literal tool-call markup
(`</content>` and `</invoke>`) had leaked onto the end of the file after the last assertion of
`test_settle_answers_the_coverage_flag_false_with_a_model__S024_005_DoD8`. **Tail corruption only —
nothing was truncated:** every test of the inventory above (DoD-1 ×1, DoD-2 ×3, DoD-3 ×2, DoD-4 ×1
parametrized over three kinds, DoD-5 ×1, DoD-6 ×2, DoD-7 ×2, DoD-8 ×6) is present, and the final
test ends with both of its recorded assertions (`factory.call_count == 1` and the construction
tuple). The two leaked lines were deleted and **no test was re-authored, and no assertion changed**;
the file is 1034 lines. The eight amended existing files were checked for the same artifact and are
clean (no `</content>` / `</invoke>` anywhere under `tests/`, and each of the eight ends on a
complete assertion). Coverage after the repair is unchanged: DoD-1 … DoD-9 ✓.

### Step 006 — tests (2026-10-04)

- `backend/tests/test_persona_setup_fanout.py` (new) — covers DoD-1 … DoD-7 — the strict persona
  and setup-description fan-out (archived sessions included), the two "unavailable" conditions with
  a full rollback, the N = 0 and no-vector-work paths for both services, and the two PATCH routes.
  Observed only from the test side.
- `backend/tests/test_characters_service.py`, `backend/tests/test_setups_service.py`,
  `backend/tests/test_characters_router.py`, `backend/tests/test_setups_router.py` — **not edited.
  No change was needed, and none was invented** (DoD-8; see the fallout finding below).
- Not touched: `conftest.py`, every step file, `context.md`, `outcome.md`, and every other test file.

Test inventory (all names end `__S024_006_DoD<n>`):

| DoD | Test(s) | Asserts |
|---|---|---|
| 1 | `test_a_changed_sheet_refreshes_every_session_of_the_character`, `test_each_refreshed_text_begins_with_the_new_sheet`, `test_the_fan_out_is_one_client_and_one_embed_call` | character C with S1 (active, setup X), S2 (**archived**, setup X) and S3 (active, no setup), one settled entry each, sheet changed to the step file's literal `"Tall, scarred, soft-spoken."`: each session's `session_vec` row **equals** `embedding_vector(<its own D6 composed text>, 8)` and the new sheet is stored; **every** text sent begins with the new sheet and contains none of the old one (D6 persona-first); and `factory.call_count == 1` with **exactly one** `embed` call carrying the model name and all three composed texts (compared as a set — the plan pins the batch, not its order), the construction carrying the designated base URL and the passed timeout. A per-session loop fails the third test (D1, U4, US-021.AC-1, US-138.AC-1) |
| 2 | `test_a_persona_edit_without_a_model_stores_nothing`, `test_a_persona_edit_with_an_unreachable_provider_stores_nothing` | with N > 0 and **no** designation → `NoEmbeddingModelError` (`code == "no_embedding_model"`); with a designation and a raising fake → `LlmUnreachableError` (`code == "llm_unreachable"`). In **both**: the stored sheet is the old one and the blob of **every** one of the three `session_vec` rows is byte-identical to a snapshot taken before — the whole transaction rolled back (D8, authoring fail-hard) |
| 3 | `test_a_sheet_change_with_no_sessions_needs_no_model` | a character with **no** sessions has its sheet changed with no designation: it succeeds, the new sheet is stored, and `factory.call_count == 0` / `embed_calls == []` (U4) |
| 4 | `test_a_name_only_character_update_does_no_vector_work`, `test_a_sheet_equal_to_the_stored_one_does_no_vector_work`, `test_creating_a_character_needs_no_model` | on a character **with** three sessions and no designation: a name-only update, and an update whose `sheet` equals the stored sheet sent with a new name, each succeed (the name persists, the sheet does not change), record **zero** constructions and zero embed calls, and leave all three blobs byte-identical; `create_character` with no designation also succeeds with the held factory recording nothing (D5 — "changed" means differs from stored) |
| 5 | `test_a_changed_description_refreshes_only_the_sessions_using_that_setup` | S1 (active, X), S2 (**archived**, X), S3 (Y), S4 (no setup), all four carrying a pre-written vector: changing X's description gives `call_count == 1` and **one** `embed` call of **two** texts, each containing the new description and none the old; the two texts are exactly S1's and S2's D6 compositions and their rows hold those vectors, while **S3's and S4's blobs are byte-identical** and the new description is stored. This is what proves the selection filters on the setup and carries no archive predicate (US-138.AC-1, U4) |
| 6 | `test_a_description_edit_without_a_model_stores_nothing`, `test_a_description_edit_with_an_unreachable_provider_stores_nothing`, `test_a_description_change_with_no_sessions_needs_no_model`, `test_a_name_only_setup_update_does_no_vector_work`, `test_a_description_equal_to_the_stored_one_does_no_vector_work`, `test_creating_a_setup_needs_no_model` | DoD-2 … DoD-4 mirrored for setups: both failure codes propagate with the old description stored and all four blobs byte-identical; a setup no session uses changes its description with no model; a name-only edit and a description equal to the stored one (sent with a new name) each succeed with zero factory calls and unchanged blobs; `create_setup` needs no model (D5, D8) |
| 7 | `test_a_sheet_patch_without_a_model_answers_409_and_keeps_the_old_sheet`, `test_a_sheet_patch_with_a_designated_model_answers_200`, `test_a_description_patch_with_an_unreachable_provider_answers_502`, `test_a_description_patch_with_no_sessions_answers_200_without_a_model` | through `create_app()` with `dependency_overrides` on the two keys the skeleton recorded (`app.dependencies.get_llm_client_factory`, `app.config.get_settings`), a route-created character / setup and a raw-inserted session making N > 0: `PATCH /api/characters/{id}` with a changed sheet and no designation → **409** `{"error": {...}}` `no_embedding_model` and a following **GET showing the old sheet**; with a designation and the fake → **200** with the new sheet, one client built, one embed call; `PATCH /api/setups/{id}` with a changed description against a raising fake → **502** `llm_unreachable` with the stored description unchanged; the same PATCH with **no** session on the setup and no model → **200** with the new description and `call_count == 0` (Wire contract, D8, U4) |
| 8 | the **existing, unedited** suites in `test_characters_service.py`, `test_setups_service.py`, `test_characters_router.py` and `test_setups_router.py` | regression fallout: all four pass unchanged under the N > 0 rule. No test was edited — see below |

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓,
DoD-8 ✓ (existing suites, **unedited**). No `[manual/live]` item in this step.

#### DoD-8 — the fallout finding: no edit was needed, and none was invented

Verified against harvest **F4** and **F3** ("Character and setup updates") rather than assumed:

- the four listed files' `sheet` / `description` update sites are `test_characters_service.py`
  L301, L316, L408 (archived) and L236 (foreign, refused); `test_setups_service.py` L441, L457,
  L551 and L376 (foreign, refused); `test_characters_router.py:418-428` and `:596-613`;
  `test_setups_router.py:536-548`, `:557-566` and `:600-608`;
- **none of those four files mentions `sessions`, `_insert_session` or `create_session` at all**, so
  N = 0 at every one of those sites, and D5's "only when N > 0" means none of them needs a
  designated model, a fake, or an override. Nothing else in them changes: no response model gained
  a field in this step, and both frozen signature changes are keyword-only **with defaults**, so
  every existing positional call still binds.
- The two source-scan guards over these services also stay green without narrowing: the `delete`
  substring guard (`test_characters_service.py:446-457`, `test_setups_service.py:625-660`) and
  `test_setups_service.py`'s `_FORBIDDEN_IMPORT = "app.services.characters"` — the step's only new
  import is `app.services.session_index`, which neither guard forbids (the skeleton re-verified
  both scans after its edit). So **no guard-narrowing deviation is needed in this step**, unlike
  steps 004 / 005.

Notes for the verifier:

- **Expect the stub signal (`NotImplementedError`) from every `update_character` and
  `update_setup` call**, the no-op and N = 0 clauses included — the skeleton record states both
  seams are reached **unconditionally** with no dispatch condition written, on purpose, so DoD-3,
  DoD-4 and DoD-6's no-vector-work tests must fail at the red gate too. A stub that skipped the
  fan-out for a name-only edit would have made them pass vacuously. The DoD-7 wire cases will
  surface the seam as a 500 rather than the pinned status — again the stub signal, not a binding
  error. The two `create_*` tests (DoD-4, DoD-6) call untouched functions and pass by their nature.
- Per `006.context.md`, a red-gate failure in any existing test file **other than the four listed
  above** is a `SPEC` hand-back, not a test fault here. `test_sessions_router.py` and
  `test_stream_router.py` are deliberately unlisted (their character / setup calls are creates, or
  edits with no sessions) and were not touched.
- DoD-1's and DoD-5's embed batches are compared **order-insensitively** (as sets, with an explicit
  length check): the plan pins "one call carried all three / two texts" and never pins the
  iteration order of the fan-out's id list.
- The factory construction tuple is pinned only on its base URL and timeout. The resolved API key
  is deliberately **not** asserted — the designation is seeded with a null `api_key_ref` and the
  plan does not fix what that resolves to.
- Conventions held: `conftest.py` untouched; no source file was read or written; the only fixtures
  are the file-local `engine`, `generator`, `wire_engine` and the routers' established autouse
  `configure_logging` neutralisation; every id is above 2^60; sessions are raw inserts **including
  an archived one (`archived_at` set)**; the designation is raw `llm_servers` / `models` rows with a
  null `api_key_ref`, so no secret resolves and no `monkeypatch.setenv` was needed; the client
  always arrives through the frozen `client_factory=` seam or the shared dependency override;
  `session_vec` is read only through `pragma_table_info`, point lookups, raw blobs and
  `struct.unpack`; the expected composed texts are built by a file-local D6 helper, never by
  calling the code under test.

### Step 007 — tests (2026-10-04)

- `frontend/tests/app/streamCoverage.test.ts` (new) — covers DoD-1 … DoD-5 — the coverage flag on
  `StreamState` as the five record-keeping effects set (or deliberately do not set) it, driven
  through `fetch` stubs keyed on method + pathname.
- `frontend/tests/app/SessionStreamCoverage.test.tsx` (new) — covers DoD-6, DoD-7 — the banner in
  `SessionStream`'s ready view, reached by driving a stubbed settle through the UI (the mechanism
  the `## Skeleton` record fixed: there is no seam to pre-set the flag).
- **No existing frontend test file needed amendment, and none was touched.** Reason, verified
  against the `## Skeleton` record and harvest C9: the wire field is **optional** (D10), so every
  existing full-`Message` builder and the `toEqual({…})` assertions on stubbed `SettleResult` /
  `ReopenResult` still hold; and the `written(state)` snapshot helper in
  `streamMutations.test.ts` / `entryEffects.test.ts` enumerates only `{ entries, zone, draft }`
  explicitly, so the new observable cannot leak into those four snapshot comparisons.
- Not touched: every source file, every other test file, every step file, `context.md`,
  `outcome.md`.

Test inventory (every `it` title ends `— DoD-N`, per the frontend test conventions):

| DoD | Test(s) | Asserts |
|---|---|---|
| 1 | `settleComposer and the coverage flag` → "a settle answered with `search_coverage_incomplete` true sets the flag, and a following successful settle answered with false clears it" | one `StreamState`, two successive successful settles on the pinned path `POST /api/sessions/<id>/settle`: `state.searchCoverageIncomplete` is `false` before the first, `true` after the `true` response, and `false` again after the `false` response — the flag tracks the latest write and does not latch (US-112.AC-2, D11) |
| 2 | `reopenLast and the coverage flag` → "a re-open answered with … true sets the flag"; "a re-open whose response omits the field reads as false and clears a previously true flag" | `POST /api/sessions/<id>/reopen` answered with the flag `true` → `true`; then a second re-open whose body **omits** the key → `false`, which is D10's absent-is-false rule asserted non-vacuously (the flag was true going in) |
| 3 | `editEntry and the coverage flag` → "an edit answered with a settled row carrying … true sets the flag"; "an edit answered with a row whose `settled_at` is null and no flag leaves a previously true flag true" | `PATCH /api/messages/<id>` answered with a row whose `settled_at` is **non-null** and the flag `true` → `true`; and, starting from a flag made true by a settle, an edit answered with a row whose `settled_at` is **null** and no flag leaves it **true** — the discrimination that proves a zone-row response never clears it (D11) |
| 4 | `filePastedPartner and the coverage flag` → "filing a pasted partner block answered with a settled row carrying true sets the flag"; "a filing answered with a zone row (`settled_at` null) does not change the flag: a previously true flag stays true" | `POST /api/sessions/<id>/entries` answered with a **settled** partner row carrying `true` → `true`; then, with the flag true, a filing answered with a row whose `settled_at` is `null` leaves it **true**. Bound to the skeleton's reading of the zone-append clause: the guard is `filed.settled_at !== null` (D11, Wire contract) |
| 5 | `a failed record-keeping request leaves the coverage flag alone` → "a settle refused with 409 `zone_empty` leaves the flag unchanged, both while false and while true" | a 409 `zone_empty` settle leaves a `false` flag `false`; a successful `true` settle then makes it `true`; a second 409 leaves it `true`. Asserted in **both** directions, so no flag write may live in a `catch` |
| 6 | `the coverage banner in the ready view` → "after a settle answered with … true, one alert holds exactly the pinned sentence, precedes the first record entry, and leaves that entry's edit control enabled"; "after the same settle answered with false, no alert and no banner sentence are rendered" | `<AppProviders><SessionStream sessionId={…}/></AppProviders>` with the stream load stubbed, the composer typed into and `Settle` pressed: exactly **one** `role="alert"` whose `textContent` **equals** `007.context.md`'s sentence verbatim; it **precedes** the record list and the settled entry's listitem in document order (`compareDocumentPosition`); that listitem's `Edit entry` button is present and **enabled**, and the `Composer` textbox is enabled — the banner disables nothing. With `false`, the settled entry is in the record (proving the write landed) and there is **no** alert and no such text (US-112.AC-2, `workspace-shell.md`) |
| 7 | `a fresh mount carries no banner` → "with a successful initial stream load and no write, no alert and no banner sentence are rendered" | a fresh mount whose two GETs succeed and which issues no write: the held entry renders and the composer is present, yet there is **no** `role="alert"` and no banner text, and every logged request is a `GET` (D11, U5 — nothing is persisted, so the flag starts false) |
| 8 | **none — `[manual/live]`** | requires-live-run: on an instance with no embedding model designated, settling shows the banner with the entry in the record and the composer usable; the next settle after a designation clears it |

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓,
DoD-8 `[manual/live]`, no test (requires-live-run).

Notes for the verifier:

- **Expected red-gate shape, as the `## Skeleton` record predicted:** no seam throws, and the
  field is contractually `false` on construction, so the clauses whose expectation is "true" fail
  (DoD-1's first half, DoD-2's first `it`, DoD-3's first `it`, DoD-4's first `it`, DoD-6's first
  `it`, and the "make it true first" preconditions inside DoD-3's / DoD-4's / DoD-5's second
  halves), while the clauses whose expectation is `false` / "unchanged from false" pass against the
  stub (DoD-2's absent case, DoD-5's first assertion, DoD-6's false half, DoD-7). That asymmetry is
  inherent, not a weak test: every "unchanged" clause is additionally asserted **from a true flag**,
  so it cannot pass vacuously once the field is written.
- Both files are bound only to the frozen interface: `StreamState.searchCoverageIncomplete` read as
  `state.searchCoverageIncomplete`; the five effect signatures unchanged; `SessionStreamProps`
  unchanged (`sessionId` only); no import of a banner component or of `COVERAGE_BANNER_TEXT` (the
  skeleton records it as **not exported**) — the sentence is a file-local constant copied from
  `007.context.md`.
- The banner sentence, the request paths and the `settled_at` discrimination all come from the plan
  (`007.context.md`, harvest report 2 A1, D10/D11), never from calling the code.
- Conventions held: Vitest/jsdom with `globals: false` (every symbol imported explicitly from
  `vitest`, `act`/`render`/`screen`/`within` from `@testing-library/react`); `tests/` mirrors
  `src/`; `fetch` stubbed with `vi.stubGlobal` keyed on `METHOD pathname`, cleaned up in
  `afterEach`; `notifyFailure` mocked through the established `vi.hoisted` pattern; all ids are
  strings above 2^60; `Message` builders carry **every** existing key (the three `tool_*` keys
  included) and add `search_coverage_incomplete` only where a DoD asks for it; the rendered
  component sits inside `<AppProviders>`.
- `npm run typecheck` was **not** run: running commands is outside the test-coder's role (execution
  is the verifier's). The files were written to the `strict` / `noUnusedLocals` rules the harvest
  records — no unused import or local, no `any`, no non-null assertion.

### Step 008 — tests (2026-10-04)

- `frontend/tests/shared/embeddingFailure.test.ts` (new) — covers DoD-1 — the pure code → sentence
  mapping, driven by `ApiError` values constructed directly (no `fetch`), plus the two exported
  constants compared against `008.context.md`'s texts written out as literals.
- `frontend/tests/app/embeddingFailureSurfacing.test.ts` (new) — covers DoD-2, DoD-3, DoD-4, DoD-5 —
  the four authoring effects against their own refusing route, each read through the channel the
  `## Skeleton` table records.
- **No existing test file needed amendment, and none was touched.** Reason, from harvest C10: every
  existing test that pins a generic sentence stubs a **generic** failure (`envelope("internal_error",
  500)` and friends), and **no existing test stubs `no_embedding_model` or `llm_unreachable`** on
  these five routes — so a code-specific sentence displaces nothing. The new third case of each group
  re-asserts those generic sentences from this file, additively.
- Not touched: every source file, every other test file, every step file, `context.md`, `outcome.md`.

Test inventory (every `it` title ends `— DoD-N`, per the frontend test conventions):

| DoD | Test(s) | Asserts |
|---|---|---|
| 1 | `the two exported sentence constants` → three `it`s | `NO_EMBEDDING_MODEL_SENTENCE` and `LLM_UNREACHABLE_SENTENCE` each **equal** the corresponding text of `008.context.md` "The two sentences (exact)", written out in the test as spec literals; and the two texts differ, so no later assertion can pass by coincidence |
| 1 | `embeddingFailureSentence — the two embedding codes` → three `it`s | `new ApiError("no_embedding_model", …, 409)` → the first sentence; the same code at 409 **carrying `detail {reason:"dimension_mismatch"}`** (D8) → the same sentence; `new ApiError("llm_unreachable", …, 502)` → the second sentence. The two code literals are typed in the test — the `## Skeleton` record states the code constants are **not** exported |
| 1 | `embeddingFailureSentence — everything else is null` → four `it`s | null for `ApiError` code `memo_not_found` (404), for `not_authenticated` (401), for a plain `Error`, and for `undefined` — the "nothing (null) for anything else" half of the Interface intent |
| 2 | `saveNote — a refused memo body edit` → three `it`s | a held note's text edited, then `saveNote(state, MEMO_ID)` against a refusing `PATCH /api/memos/<id>`: 409 `no_embedding_model` → `noteFailure(state, memoId)` is `NO_EMBEDDING_MODEL_SENTENCE`; 502 `llm_unreachable` → `LLM_UNREACHABLE_SENTENCE`; 500 `internal_error` → `"Could not save the note."` **unchanged**. Each also asserts exactly one request, `PATCH` on that pathname, and that the effect resolves without rejecting |
| 3 | `saveNewNote — a refused memo create` → three `it`s | `openNewNote` + `setNewNoteText` + `saveNewNote(state)` against a refusing `POST /api/memos`, same three cases, read as `state.newNote?.failure`, generic `"Could not save the note."` |
| 4 | `commitPersona — a refused persona save` → three `it`s | a loaded screen whose `sheet` was changed, `commitPersona(state, characters)` against a refusing `PATCH /api/characters/<id>`, same three cases, read as `state.error`, generic `"Could not save the character."`. Bound to **`commitPersona`** per `## Ultra phase` (3) and the `## Skeleton` binding correction — the step file's `submitSave` does not exist |
| 5 | `submitSetup — a refused setup create` → three `it`s | a create-mode `new SetupDraft(CHARACTER_ID, null)` with both fields typed, `submitSetup(draft, onSaved)` against a refusing `POST /api/characters/<characterId>/setups`, same three cases, read as `draft.error`, generic **`"Could not create the setup."`**; `onSaved` is never called |
| 5 | `submitSetup — a refused setup save` → three `it`s | an edit-mode `new SetupDraft(CHARACTER_ID, TAVERN)` with both fields changed, against a refusing `PATCH /api/setups/<setupId>`, same three cases, read as `draft.error`, generic **`"Could not save the setup."`** — the sentence that differs from the create path, chosen by `draft.original === null`; `onSaved` is never called |
| 6 | **none — `[manual/live]`** | requires-live-run: on an instance with no embedding model designated, creating a note shows the `no_embedding_model` sentence and creates nothing, and editing the persona of a character that has sessions shows the same sentence and keeps the old persona |

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 `[manual/live]`, no test
(requires-live-run).

Notes for the verifier:

- **Expected red-gate shape, exactly as the `## Skeleton` record predicted: DoD-1 passes in full**
  against the skeleton, because the helper and both constants are delivered there (a pure total
  three-branch mapping with no seam). That is by design, not a test fault.
- DoD-2..5: the **third `it` of each group passes** (the generic fallback is the delivered
  behaviour), and the **first two of each group fail** — eight assertions, each failing with
  "received the generic sentence" rather than the pinned one. No throw, no timeout, no type error:
  the skeleton's seam does not throw, and all four effects still resolve.
- The third case is not vacuous cover: it is the regression half DoD-2..5 ask for in so many words
  ("a stubbed 500 with another code surfaces the pre-existing generic sentence, unchanged"), and it
  is what proves the change is additive.
- Bound only to the frozen interface: `embeddingFailureSentence(error: unknown): string | null` with
  the two exported constants (the two **non-exported** code constants are never imported — the
  literals are typed in the test); `saveNote(state, memoId)`, `saveNewNote(state)`,
  `commitPersona(state, characters)`, `submitSetup(draft, onSaved)` — every signature unchanged; the
  channels read as `noteFailure(state, memoId)`, `state.newNote?.failure`, `state.error`,
  `draft.error`. Nothing out of scope is touched: no blank→DELETE branch, no flag toggle, no
  reorder, no `commitName`, no `submitCreate`.
- **No notification mock is registered**, since the `## Skeleton` record states none of the four
  effects calls `notifyFailure`.
- Conventions held: `globals: false` — every Vitest symbol imported explicitly; `tests/` mirrors
  `src/` (`tests/shared/` is new and, per harvest C12, unconstrained by any file-inventory scan);
  `fetch` stubbed with `vi.stubGlobal` keyed on `METHOD pathname` and cleaned up in `afterEach`
  (`vi.unstubAllGlobals` + `vi.restoreAllMocks`); any request to an unstubbed route is answered with
  a code that is **neither** embedding code, so a wrong-route request cannot make a test pass; all
  ids are decimal strings above 2^60; no `any`, no non-null assertion, no unused import or local.
- `npm test` and `npm run typecheck` were **not** run: running commands is outside the test-coder's
  role (execution is the verifier's).

## Notes & Issues

_populated by the coder when worth saying_

## Ultra phase

- orient: done 2026-10-04
- policy (carried from 023, user 2026-10-03): mechanical knock-on test amendments outside a
  step's Test files are approved deviations, recorded under that step's `## Tests`.
- regression-fallout protocol (this feature's `context.md`): each step lists the existing
  test files it may fix. **A red-gate failure in an UNLISTED existing file is a `SPEC`
  hand-back to the orchestrator**, who extends that step's Test files. No agent edits an
  unlisted file on its own judgment.
- harvest: done — docs/.cache/ultra/024.embedding-lifecycle/harvest.md (2 reports)

### Two conflicts the harvest surfaced at orient, both resolved before any code

**(1) Service-import guards vs. the plan's required imports — user decision, 2026-10-04:
narrow the three guards.** The plan requires `services/memos.py` to import
`app.services.embedding`, and `services/settle.py`, `services/characters.py` and
`services/setups.py` to import `app.services.session_index`
(`005.context.md`, `006.context.md` call these deliberate additions). Delivered guards forbid
exactly that: `test_memos_service.py:846`/`:1208` (no `app.services` import at all) and
`test_settle_service.py:930` (only `parens` + `llm.chat.strip_think`). Each guard is narrowed
to permit **only the one new named import**; every other `app.services` import stays an
offender, so the invariant still bites. Recorded as approved deviations under the owning
steps' `## Tests` (004 and 005/006).

Also noted for the coders, from harvest F2: `services/characters.py` and `services/setups.py`
are source-scanned for the substring `delete` (**case-insensitive, comments included**), and
`services/memos.py` for the substring `title`. Neither module may contain those strings — the
fan-out reaches `delete_vector` only indirectly through `session_index`, which is fine.

**(2) `MessageResponse`'s new field breaks four UNLISTED files — orchestrator decision under
this feature's own regression-fallout protocol.** Harvest F2 found `MessageResponse` pinned to
exactly 11 keys in seven files. Step 005 lists `test_stream_router.py` and
`test_stream_models.py`; it does **not** list `test_sessions_router.py`,
`test_discussion_read.py`, `test_tool_rows.py` or `test_tool_wire_fields.py`. Per
`context.md`'s protocol ("the orchestrator then extends that step's Test files"), **step 005's
Test files are extended by those four**, for the key-set assertions only.

**(3) Step 008 names a function that does not exist — orchestrator refinement, 2026-10-04.**
`008.authoring-failure-sentences.md` binds the character surface to `submitSave` (~L185) in
`characterScreenState.ts`. Harvest report 2 Correction 1: **there is no `submitSave`**; L185 is
the doc comment of `applyFieldSave`. The character-save surfaces are `commitName` (L96) and
`commitPersona` (L147), both writing `SAVE_FAILED` to `state.error`. **Step 008 binds to
`commitPersona`**, because D5 embeds only on a **changed `sheet`** — a name-only edit and a
create do no vector work, so `commitPersona` is the only one that can receive
`no_embedding_model` / `llm_unreachable`. The DoD's intent is unchanged; only its function name
was wrong.

**(4) A fourth import guard of the same kind — orchestrator applies the user's stated
principle, 2026-10-04.** `services/messages.py` must import `app.services.session_index`
(step 005), and `tests/test_messages_service.py:1126` fails **any** `app.services*` import.
The user's 2026-10-04 decision named three guards (`test_memos_service.py:846`/`:1208`,
`test_settle_service.py:930`); this fourth one was **under-reported by the orchestrator** when
the decision was put to the user. It is the identical situation — same class of guard, same
remedy — and `test_messages_service.py` is **already** one of step 005's declared Test files,
so this is not even an out-of-scope deviation. The user's stated principle is applied verbatim:
narrow the guard to permit **only** `app.services.session_index`; every other `app.services`
import stays an offender. Recorded under step 005's `## Tests`.
- skeleton: done — steps 001, 002, 003, 004, 005, 006, 007, 008
- tests: done — steps 001, 002, 003, 004, 005, 006, 007, 008 (approved deviations: four service-import guards narrowed to one named import each; `MessageResponse` key sets repaired in 7 files; step 005's Test files extended by 4)

**(5) A fifth `MessageResponse` key-set file — orchestrator decision, red gate run 1.** The gate
found `backend/tests/test_sessions_models.py` failing with a `ValidationError` in
`..._started_response_with_a_message_serialises_the_eight_key_message__S018_001_DoD6__S022_001_DoD4`
and `..._started_response_accepts_a_message_response__S018_001_DoD6__S022_001_DoD4`: 018's
`StartedSessionResponse.opening_message` embeds `MessageResponse`, which now requires
`search_coverage_incomplete`. This is the **same family** as conflict (2)'s four files and was
**missed by the orchestrator** when scope was first extended. Per `context.md`'s protocol,
**step 005's Test files are extended by `test_sessions_models.py`** as well. Unlike the three
other unlisted failing files it will **not** go green on implementation alone.

For the record, three further existing files are on no step's Test list and fail **only** on
`NotImplementedError` from the deliberate stubs — `test_bootstrap_router.py` (28),
`test_settle_tool_rows_and_think.py` (12), `test_translation_invalidation.py` (6). They need
**no edit** and go green once steps 001 and 005 are coded; noted as a scope-list omission only.
- red-gate: PASS (run 2) — run 1 FAIL: SPEC scope hand-back, `test_sessions_models.py` was a fifth `MessageResponse` key-set file (resolved as conflict (5)); no step ever had a TEST fault
- code: done — steps 001, 002, 003, 004, 005, 006, 007, 008 (no re-freeze, no escape valve)
- verify: PASS (run 2) — 7814 tests, 0 failures (backend 3794, frontend 4020); run 1 FAIL: 005 TEST (two legacy whole-object comparisons contradicted the feature's own wire contract); 2 `[manual/live]` outstanding (007 DoD-8, 008 DoD-6)
