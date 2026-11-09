# Fast feature 002 — vector-index-rebuild — plan

**Delivers:** FEAT-005, UC-016, US-019.AC-1. Read `context.md` first.

## Goal

An administrator presses **Rebuild index** on the Database page, confirms, and the instance drops and re-derives both vector tables and both FTS5 indexes from the source rows of every user in one all-or-nothing transaction; the page reports completion (or the failure) and nothing derived from user content.

## Source files

```
backend/app/db/search_tables.py        — add public helpers: drop the two vector tables; rebuild both FTS indexes' contents
backend/app/services/index_rebuild.py  — new; the rebuild orchestration and the embed batch-size constant
backend/app/models/admin_db.py         — add the rebuild response model
backend/app/routers/admin_db.py        — add POST /rebuild; update the module docstring
frontend/src/admin/databasePageState.ts — rebuild observable fields + the rebuild free function
frontend/src/admin/DatabasePage.tsx     — Rebuild index button, ConfirmModal, completion line, failure Alert
```

## Test files

New:

```
backend/tests/test_admin_db_rebuild.py
frontend/tests/admin/databasePageRebuild.test.ts
frontend/tests/admin/DatabasePage.rebuild.test.tsx
```

Update existing (amendment 2026-10-07; these encode the earlier "no rebuild surface" rule that this feature deliberately overturns — change only what that rule forces, weaken nothing else; covered by DoD-22):

```
backend/tests/test_admin_db_router.py          — add POST /rebuild to the closed route set (test_router_declares_exactly_the_expected_routes__DoD3) and to the no-path-parameter branch (test_router_declares_no_query_parameter_and_no_non_table_key__DoD3); in test_route_surface_has_no_rebuild_or_vector_route_and_one_import_route__DoD14 drop the no-rebuild half and keep the one-import-route half; narrow or retire test_route_surface_documents_nothing_about_a_vector_index__DoD14 (the rebuild route legitimately documents vectors); remove the POST-/api/admin/database/rebuild case from test_out_of_scope_routes_do_not_exist__DoD14
backend/tests/privacy_audit_support.py         — feature 032's enumeration: classify the rebuild route (row 74, owner fast/002, currently [blocked/unbuilt-dependency]) as built, update EXCLUDED_ROWS (now {5, 74}) and EXPECTED_ROW_COUNT accordingly, remove row 74 from the unbuilt guard
backend/tests/test_privacy_audit_routes.py     — only as needed so test_app_routes_and_the_enumeration_agree_exactly__S032_002_DoD1 and test_no_unbuilt_surface_has_landed__S032_002_DoD1 reflect the built rebuild route
backend/tests/test_privacy_audit_admin.py      — only as needed so test_every_admin_read_carries_only_administrative_data__S032_006_... reflects the built rebuild route; its DoD-7 slot owned by fast/002 now covers the rebuild response carrying no content-derived count (this plan's DoD-14)
frontend/tests/admin/databasePage.test.tsx     — in "nothing out of scope on the page" allow the Rebuild index control and its wording (4 tests; add Rebuild index to the allowed controls outside the table); add rebuildStatus, rebuildErrorMessage, rebuildComplete to the ALLOWED_FIELDS allowlist
frontend/tests/admin/databaseActions.test.tsx  — remove or invert "no control anywhere on the page is named Rebuild or Re-index — DoD-14"; add rebuildStatus, rebuildErrorMessage, rebuildComplete to the ALLOWED_FIELDS allowlist
```

## Interface intent

### Backend

- **`drop_vector_tables`** (in `db/search_tables.py`) — given a connection, drops `memo_vec` and `session_vec` if they exist. Absent tables are not an error. Executes inside the caller's transaction (no commit of its own). Pairs with the existing `ensure_vector_tables(conn, dim)` for re-declaration.
- **`rebuild_fts_indexes`** (in `db/search_tables.py`) — given a connection, ensures both FTS tables and their triggers exist (via `ensure_fts_tables`), then rebuilds `memo_fts` from all of `memos.body` (FTS5 `'rebuild'` is acceptable here) and rebuilds `message_fts` by deleting all its rows and re-inserting record rows only — the same record predicate the existing message back-fill uses. Must never use `'rebuild'` on `message_fts`. Runs in the caller's transaction.
- **`REBUILD_EMBED_BATCH_SIZE`** (module constant in `services/index_rebuild.py`) — maximum number of texts sent in one `embed_texts` call. A small fixed integer (coder's choice, e.g. 32–64). Tests may monkeypatch it.
- **`rebuild_index`** (in `services/index_rebuild.py`) — inputs: a connection, an LLM client factory, a request timeout in seconds. Opens one transaction and in it: validates the designation (raising the existing `NoEmbeddingModelError` → 409 `no_embedding_model` when none); opens the embedding handle to learn `embedding_dim`; drops and re-creates both vector tables at that dimension; embeds every memo with a non-blank body (all users) and writes its vector keyed by memo id; embeds every session whose composed text (`compose_session_text` with that session's owning user id) is non-empty and writes its vector keyed by session id; texts are embedded in chunks of at most `REBUILD_EMBED_BATCH_SIZE`, a fresh handle per chunk; then calls `rebuild_fts_indexes`. Memo eligibility mirrors the memo write path (`_refresh_memo_search_rows`); if that path excludes any memo class beyond blank bodies, the rebuild mirrors it. Any raised error (no designation, unreachable server, dimension mismatch from the provider, secret-ref failure) propagates unchanged and rolls the whole transaction back. Output: the rebuild report model.
- **Rebuild report model** (in `models/admin_db.py`) — one field, `tables_rebuilt`: the list of the four derived table names (`memo_vec`, `session_vec`, `memo_fts`, `message_fts`), always the same four, in that order. No other field. Its content never depends on how much data exists.
- **`POST /api/admin/database/rebuild`** (in `routers/admin_db.py`) — sync `def`, inherits router-level `require_admin`, takes `get_connection`, the LLM client factory dependency (`get_llm_client_factory`) and settings' `llm_request_timeout_seconds`; calls `rebuild_index` once; no try/except; answers 200 with the report model. No request body. The module docstring's "no rebuild route" line is replaced with a one-line description of the route.

### Frontend

- **Rebuild fields on the Database page state class** — a status union for the operation (idle / rebuilding), a per-operation error slot (string or null), a completion flag (true after a successful rebuild, cleared when a new rebuild starts), and whatever confirm-open flag the page's existing Import confirm pattern uses. Observable fields only.
- **`rebuildIndex`** free function — inputs: the state, an optional abort signal. Sets the status to rebuilding and clears error and completion; POSTs `/api/admin/database/rebuild` via `apiPost`; on success sets completion true; on failure stores `failureMessageOf(error, <fallback>)` in the rebuild error slot; always returns status to idle; never rejects; all mutation inside `runInAction`. It does not touch the drift report, export or import state.
- **Database page** — a **Rebuild index** button in the page-level action group beside Export and Import (the reserved spot at `DatabasePage.tsx:161-162`). Never disabled by drift state or by the drift report's loading/error state; disabled only while a rebuild is in flight. Clicking opens `ConfirmModal` with a title and a one-sentence consequence naming the expense (re-embeds every memo and session; takes time; makes metered calls to the embedding provider), a confirm label, and `loading` true while the request is in flight. Cancel closes without a request. On success the modal closes and a dimmed text line says the rebuild is complete. On failure the modal closes and the message shows in the rebuild's own inline red `Alert`, separate from the drift report's and import's error slots. No notification.

## Definition of done

1. **DoD-1** `[test]` — An admin `POST /api/admin/database/rebuild` with an embedding model designated answers 200 with a body whose only key is `tables_rebuilt`, equal to `["memo_vec", "session_vec", "memo_fts", "message_fts"]`.
2. **DoD-2** `[test]` — After a rebuild, every memo with a non-blank body (memos owned by at least two different users) has a vector in `memo_vec`, and no memo with a blank body has one.
3. **DoD-3** `[test]` — After a rebuild, every session with non-empty composed text (sessions owned by at least two different users) has a vector in `session_vec`.
4. **DoD-4** `[test]` — A vector row in `memo_vec` or `session_vec` whose id matches no existing memo/session before the rebuild is absent after it.
5. **DoD-5** `[test]` — When `memo_vec`/`session_vec` exist at a dimension different from the designated model's, a rebuild leaves both tables at the designated dimension (per `vector_table_dimension`) and populated.
6. **DoD-6** `[test]` — When both vector tables are absent (e.g. as after a whole-database import), a rebuild creates them at the designated dimension and populates them.
7. **DoD-7** `[test]` — With `REBUILD_EMBED_BATCH_SIZE` patched below the number of memos, a rebuild still writes a vector for every eligible memo and session (chunk boundaries lose nothing).
8. **DoD-8** `[test]` — After a rebuild, `memo_fts` matches a word from a memo body whose FTS row had been deleted beforehand, and `message_fts` matches a word from a record (settled, non-related) message whose FTS row had been deleted beforehand.
9. **DoD-9** `[test]` — After a rebuild, `message_fts` contains no row for an unsettled (zone) message nor for a message with `related_to` set.
10. **DoD-10** `[test]` — After a rebuild, creating a new memo through the normal API makes it FTS-searchable (triggers are in place).
11. **DoD-11** `[test]` — With no embedding model designated, the route answers 409 with code `no_embedding_model`, and the vector tables' rows and dimension and the FTS contents are unchanged.
12. **DoD-12** `[test]` — With an unreachable embedding server (`unreachable_factory`), the route answers the error status the existing error model assigns to an unreachable LLM, and the previous vector rows, vector table dimensions and FTS contents are all unchanged (all-or-nothing).
13. **DoD-13** `[test]` — A roleplayer `POST /api/admin/database/rebuild` is refused with 403; an unauthenticated one with 401; neither changes any vector row.
14. **DoD-14** `[test]` — The response body is identical for an instance with no memos/sessions and one with several — no count derived from user content, and no memo/session text appears in it.
15. **DoD-15** `[test]` — Store: `rebuildIndex` on a 200 sets the completion flag, leaves the error slot null, ends with status idle, and POSTs exactly `/api/admin/database/rebuild`.
16. **DoD-16** `[test]` — Store: `rebuildIndex` on a 409 `no_embedding_model` (and on a network failure) stores a non-empty message in the rebuild error slot, leaves completion false, ends idle, does not reject, and leaves the drift-report / import error slots untouched.
17. **DoD-17** `[test]` — Page: the Rebuild index button renders in the page-level action group and is enabled whether the drift report shows drifted/missing rows, all in sync, or is still loading.
18. **DoD-18** `[test]` — Page: clicking Rebuild index opens a confirm whose consequence text mentions the expense; Cancel closes it and sends no rebuild request.
19. **DoD-19** `[test]` — Page: confirming sends the POST; while it is pending the confirm is in its loading state; on 200 the confirm closes and a "rebuild complete" line appears; no count is shown.
20. **DoD-20** `[test]` — Page: confirming against a failing route closes the confirm and shows the failure in an inline alert distinct from the drift report's alert.
21. **DoD-21** `[manual/live]` — Against a real designated embedding server, a rebuild after changing the designation to a model of a different dimension completes, and `memo_search` / `session_search` return results afterwards.
22. **DoD-22** `[test]` — (amendment 2026-10-07) The pre-existing route-surface, privacy-enumeration and store-allowlist tests listed under "Update existing" in Test files are updated to the new surface: `POST /api/admin/database/rebuild` is part of the admin router's closed route set and of feature 032's privacy enumeration as a built, fast/002-owned admin route whose response carries no content-derived count; the Rebuild index control and the three rebuild store fields are allowed on the Database page. The full backend suite (`<py> -m pytest`) and full frontend suite (`npm test`) are green, and no other assertion in those files is removed or weakened (only the "no rebuild / no vector-index surface" assertions change).

## Out of scope

- Any standalone script or CLI rebuild (declined in `brief.md` and `admin-surfaces.md`).
- Forcing or prompting a rebuild on designation change; any staleness marker or banner.
- A job runner, background task, progress stream or cancel control.
- Adding the virtual tables to the drift report.
- Changing how `SecretRefError` maps to a status (defect D-03).
- Changing the memo/session write paths or `ensure_vector_tables`' mismatch behaviour.
- Editing any pre-existing test beyond what the overturned "no rebuild surface" rule forces (DoD-22).
