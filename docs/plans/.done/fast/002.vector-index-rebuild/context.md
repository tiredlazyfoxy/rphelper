# Fast feature 002 — vector-index-rebuild — context

**Delivers:** FEAT-005, UC-016, US-019.AC-1. Requirements are cited, not restated; open `docs/product/` for behaviour.

**Boundary:** `brief.md` (read-only). In: the rebuild route and the Database page's rebuild control with its confirm and completion reporting. Out: any standalone script or CLI; prompting for or forcing a rebuild when the embedding designation changes.

## Architecture this binds to

- `docs/architecture/search-and-retrieval.md` "Index rebuild — FEAT-005" (:1134-1195): the five rebuild steps (validate designation → re-declare `vec0` at the designated dimension → re-embed every memo and session for every user → rebuild FTS5 → report completion); the privacy narrowing (report = completion plus at most counts **not** derived from user content); changing the designation neither forces nor prompts a rebuild.
- `docs/architecture/admin-surfaces.md` (:562-734): Rebuild index joins the page-level action group beside the Database title (with Export, Import); always available — never gated on drift state nor on a designation being present (no designation → runs and fails with `no_embedding_model`); takes the shared confirm; failures in their own inline red `Alert`, never a notification; rebuild-after-Sync repairs stale FTS (the Sync drop takes FTS triggers with it), rebuild-after-restore re-creates the vector tables the import dropped. No CLI equivalent.
- `docs/architecture/forms-and-lists.md` confirm table (:345): the confirm's consequence is expense — re-embeds every memo and session, real time and real metered calls.
- `docs/architecture/frontend-structure.md` (:203-207): the `admin` entry renders no count or preview of user content (UC-066, R5).

## User-confirmed decisions (from the orchestrator)

1. One blocking `POST /api/admin/database/rebuild` (sync `def`). Button + `ConfirmModal` held in its loading state until the request returns. No job runner, no progress stream.
2. One transaction — all-or-nothing. Any failure leaves the previous index (vector rows, vector table dimensions, FTS contents) exactly as it was.
3. Response carries completion and at most content-free counts. Chosen shape: the fixed list of the four derived table names rebuilt. Never memo / session / row counts, never per-user data.
4. Always available. No designation → 409 `no_embedding_model`, shown on the page as a failure.

## Planner choices and reasons

- **Always drop and re-create both `vec0` tables** at the designated model's `embedding_dim`, rather than only when the dimension differs. Reason: the rebuild must also clear vectors for rows that no longer exist and vectors produced by a superseded model at the same dimension; a drop makes "every vector came from this rebuild" true by construction, and it also covers the post-import case where the tables are absent.
- **Order inside the transaction:** validate designation and open the handle (no network) → drop + re-create vector tables (takes the write lock first, so no concurrent writer slips a vector into a table about to be dropped) → embed and write memo vectors → embed and write session vectors → rebuild FTS → return report. Holding the write lock across embedding calls is accepted: this is a rare, confirmed admin operation, and decision 2 requires one transaction.
- **Chunked embedding:** a fixed module-level batch-size constant; each chunk uses a fresh handle from `open_embedding_model` because a handle is not reusable across `embed_texts` calls. Reason: one HTTP request for every memo in the instance risks provider payload limits and the request timeout.
- **FTS:** `memo_fts` via FTS5's `'rebuild'` command (external content is all of `memos.body`). `message_fts` must **not** use `'rebuild'` — its external content table is `messages`, and `'rebuild'` would index zone and buried rows; instead delete-all then re-insert record rows only (`settled_at IS NOT NULL AND related_to IS NULL`), the same predicate `_MESSAGE_FTS_BACK_FILL` uses. Then re-issue the triggers (`ensure_fts_tables` does `IF NOT EXISTS`), which repairs triggers lost to a Sync.
- **Placement:** a new service module `services/index_rebuild.py` owns the orchestration; table-level DDL helpers (drop vector tables, rebuild FTS contents) are added as public functions in `db/search_tables.py` beside the private constants they need, so the service does not reach into private names.

## Code facts (from the harvest; paths under `backend/app/` unless noted)

- `db/search_tables.py`: derived tables live outside `metadata` — `memo_fts` (FTS5 external content over `memos.body`, rowid = `memos.id`), `message_fts` (external content over `messages.text`, record rows only), `memo_vec` (`vec0`, `memo_id` PK, `FLOAT[dim]`), `session_vec` (`vec0`, `session_id` PK). Public: `ensure_fts_tables(conn)` (creates + back-fills only on creation, re-issues triggers IF NOT EXISTS), `vector_table_dimension(conn, name)` (int or None), `ensure_vector_tables(conn, dim)` (raises `NoEmbeddingModelError(dimension_mismatch)` on mismatch; nothing drops a vec table today), constants `MEMO_VEC_TABLE`, `SESSION_VEC_TABLE`, `MEMO_FTS_TABLE`, `MESSAGE_FTS_TABLE`. Private: `_MEMO_FTS_BACK_FILL`, `_MESSAGE_FTS_BACK_FILL` (:55-58), `_VECTOR_KEY_COLUMNS`. DDL is transactional (isolation_level=None + BEGIN listener), so drop/create roll back with the transaction.
- Write paths: `services/memos.py:317 _refresh_memo_search_rows` embeds the raw body; blank body → `delete_vector`. `services/session_index.py:70 compose_session_text(conn, user_id, session_id)`; `:130 refresh_session_vectors` is owner-scoped (unsuitable for an all-users loop). No unscoped "all memos / all sessions" lister exists — the service queries the tables directly (memo id + body; session id + owning user id).
- `services/llm_registry.py:645 validate_embedding_model(conn)` raises `NoEmbeddingModelError` (409 `no_embedding_model`).
- `services/embedding.py`: `open_embedding_model(conn, *, client_factory, timeout_seconds)` → handle with `client`, `model_name`, `embedding_dim` (no network; may raise `SecretRefError`); `embed_texts(handle, texts)` one HTTP request per call, handle single-use, raises `LlmUnreachableError` / `NoEmbeddingModelError(dimension_mismatch)`; `write_vector(conn, table, id, vec)`; `delete_vector`.
- Routers pass `settings.llm_request_timeout_seconds` and `client_factory` from `Depends(get_llm_client_factory)` (pattern: `routers/memos.py:114,131`).
- `routers/admin_db.py`: prefix `/api/admin/database`, router-level `require_admin`; sync `def` handlers call one service function, no try/except (errors map through the global error model); `get_connection` dependency opens no transaction — services do `with connection.begin()`. Models in `models/admin_db.py`. Module docstring (:19-24) currently says there is no rebuild route.
- Frontend `frontend/src/admin/DatabasePage.tsx` + `databasePageState.ts`: MobX class holds observable fields only (pure data contract); a status union per operation (e.g. `exportStatus: "idle" | "exporting"`) and a per-operation error slot; free functions `(state, signal?)` mutate inside `runInAction`, never reject, use `failureMessageOf(error, fallback)` and `apiPost` from `../shared/api`. Action group at `DatabasePage.tsx:163-190` (comment :161-162 reserves Rebuild's place). `shared/ConfirmModal.tsx` props: `opened, title, consequence, confirmLabel, confirmColor?, loading?, onCancel, onConfirm`. Failures as inline red `Alert`; success as a dimmed `Text` line; no notifications on admin pages.
- Tests: backend uses real `create_app`, tmp DB, admin and roleplayer clients, fake embedding via `get_llm_client_factory` override (`backend/tests/llm_fakes.py`: `FakeClientFactory`, `fake_factory(dim)`, `unreachable_factory`). Frontend `frontend/tests/admin/` splits page half `DatabasePage.<op>.test.tsx` and store half `databasePage<Op>.test.ts`; vitest + testing-library; fetch stubbed by method + path.

## Constraints

- Privacy (UC-066, R5): the response and the page never carry memo / session / row counts, samples, per-user breakdowns or any text derived from user content.
- `mypy app` and `npm run typecheck` are gates. TypeScript only.
- `SecretRefError` mapping (defect D-03 territory) is not changed by this feature; whatever the global error model does with it today stands.
- Test-coders may lack a shell: ruff and typecheck are the verifier's gate.
