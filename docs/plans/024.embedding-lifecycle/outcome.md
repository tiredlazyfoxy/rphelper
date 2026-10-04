# Feature 024 — Embedding lifecycle · intended documentation changes

Planner section: the doc changes the architect applies once 024 ships. Grouped by target
file. "Dn" refers to a `context.md` decision in this folder, and "Un" to a user-confirmed
decision recorded there.

## `docs/architecture/data-model.md`

| Section | Intended change | Reason |
|---|---|---|
| Identifiers — the sparse-rowid `_TBD:` | **Close it.** Snowflake ids stay the `vec0` and FTS5 keys, and there is no surrogate key. Empirical result (sqlite-vec 0.1.9, SQLite 3.47.1, 5000 × 768-d): insert, size and unfiltered KNN are identical for dense and snowflake ids, and FTS5 external content with conditional triggers passes `integrity-check` at ~2^60. **Recorded defect:** vec0 KNN with a pushed-down id constraint (`embedding MATCH ? AND k = ? AND <id> IN (...)`) silently drops true candidates for ids above ~2^50 (false negatives only, in 18–36% of queries). That form is **forbidden**. See the `search-and-retrieval.md` row for the correct forms. Record the flip condition: a sqlite-vec release that fixes pushdown at large rowids | D3, U6 |
| Vector tables | As built: `memo_vec` / `session_vec` are created by ensure-on-write (`db/search_tables.py`) at the designated `embedding_dim`, never in `db/schema.py`. The dimension is read back from the stored DDL. A mismatch is `no_embedding_model` with `detail {"reason": "dimension_mismatch"}`, and only the rebuild re-declares. Upsert is delete-then-insert or UPDATE, because `INSERT OR REPLACE` fails on vec0 0.1.9 | D2, D4, D8 |
| Vector tables — session text | As built: the order is persona, then setup text (when present), then settled entries in id order. Empty parts are dropped and the rest joined with a blank line. Persona and setup lead so model-side truncation of long sessions cannot drop them (US-138.AC-2). An empty composed text means no `session_vec` row | D6 |
| FTS5 tables | As built: only `memo_fts` and `message_fts` exist. **`session_fts` is deferred**: `sessions` has no `title` / `partner_label` columns, so it waits for the feature that gives a session text columns (FEAT-017's plan or earlier) | U7 |
| FTS5 tables — triggers | Record the exact conditions. `memo_fts`: insert, delete, and `UPDATE OF body` only, so toggles and reorders do not churn it. `message_fts`: insert when born a record row; **one** update trigger that first issues `'delete'` with OLD values iff OLD was a record row, then inserts NEW iff NEW is a record row; delete iff OLD was a record row. Record that an unconditional update trigger corrupts external-content FTS5. Back-fill on creation: `memo_fts` via `'rebuild'`, `message_fts` via INSERT…SELECT of record rows (`'rebuild'` would index zone rows) | D2, `001.context.md` |
| Schema drift and rebuild | Add: virtual tables live outside `metadata`, in `db/search_tables.py`, and are ensured inside the triggering write's transaction. That is not startup DDL, so the "no DDL at startup" rule holds. **Risk to record:** a drift-page Sync rebuild of `memos` or `messages` (create-copy-drop-rename) drops that table's FTS triggers. The next ensure restores the triggers, but does not back-fill an existing FTS table, so that index is stale until the rebuild's step 4 | D2 |

## `docs/architecture/search-and-retrieval.md`

| Section | Intended change | Reason |
|---|---|---|
| The sparse-rowid verification item | Replace it with the resolution, cross-referencing `data-model.md`. **For `025`:** the correct vector-arm forms are either (a) a scan over the candidate set, `SELECT memo_id FROM memo_vec WHERE memo_id IN (SELECT id FROM candidates) ORDER BY vec_distance_l2(embedding, :q) LIMIT :n`, which is exact and fast for hundreds of rows, or (b) an over-fetching KNN, then a JOIN to candidates or a `+memo_id IN (...)` (the unary plus blocks pushdown). **The "Query shape" example's step 2a is exactly the forbidden form** and must be rewritten. The FTS5 lexical arm is unaffected | D3, U6 |
| The invalidation fan-out — archived `_TBD:` | **Close it:** archived sessions **participate** (no archive predicate), so a restored session is never silently stale | U4 |
| The invalidation fan-out | Add: validation and fail-hard apply **only when N > 0**, where N means at least one non-empty session text to embed. Creating a character or setup, editing one with no sessions, a name-only edit, and an unchanged sheet / description need no model. A fan-out sends **one** embed request carrying all N texts | D1, D5, D6 |
| The invalidation fan-out — progress `_TBD:` | Stays open | — |
| Embedding lifecycle — trigger table | Add the as-built rows: "memo body sent but unchanged → nothing", "memo body blank → no vector (row removed)", "memo delete → its `memo_vec` row removed, no model needed", "partner filing → the session's `session_vec` row (degraded)", "character / setup create, name-only edit → nothing" | D5, D7 |
| Failure mode | The degraded path catches **`llm_unreachable` as well as `no_embedding_model`** (including dimension mismatch). The strict path propagates both (409 / 502) | U3, D8 |
| Failure mode — staleness `_TBD:` | **Answer it:** no marker and no column. A failed degraded embed leaves any existing `session_vec` row stale. The remedy is the whole-index rebuild (UC-016) | U5 |
| Embedding lifecycle (new subsection) | The mechanism: the relational write, the composition read inside the same transaction after the write, the embed call through a sync `asyncio.run` bridge, and the vector write all happen inside the service's one transaction. **Cost:** the SQLite write lock is held across the provider round trip, so concurrent writers wait. Record the flip condition: if that wait becomes visible, mark-stale-plus-rebuild (already the recorded runner-up) | D1, U1 |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| Layout | Add `db/search_tables.py`, `services/embedding.py` and `services/session_index.py` | D2, `002`, `003` |
| The two transaction rules | Extend the table with **persona / setup-text edit → fails** and **partner filing → degraded**. Name both caught errors (`no_embedding_model`, `llm_unreachable`) | D5, D8 |
| The first async code in the backend | Add the second async consumer: sync services call `LlmClient.embed` through `asyncio.run`. That is legal because routes are sync `def` on threadpool threads, and they must stay so. There is one client and one `embed` call per write operation | D1 |
| Routers versus services / dependencies | `get_llm_client_factory` now lives in `app/dependencies.py`, and `routers/admin_llm.py` re-imports the same object. Routes touched by 024 depend on it plus `get_settings`. Services take the factory and timeout as keyword-only parameters with defaults | D9 |
| Routers versus services | Record the deliberate service-to-service imports: `memos`, `settle`, `messages`, `characters` and `setups` import `services/embedding.py` / `services/session_index.py` | D9 |
| Stream routes — wire | `SettleResponse`, `ReopenResponse` and `MessageResponse` gain `search_coverage_incomplete: bool`. It is false for zone rows and appends | Wire contract |
| Error model | `no_embedding_model` gains a raise site with `detail {"reason": "dimension_mismatch"}`. That detail is instance-level, not user-scoped | D8 |
| `llm-and-streaming.md` cross-reference | "Both use-time validators ship with no call site": the embedding validator now has callers (024). The note should say so | `002` |

## `docs/architecture/workspace-shell.md`

| Section | Intended change | Reason |
|---|---|---|
| The stream — coverage banner | As built: the banner is driven by the **latest record-keeping write's response in this view** (settle, re-open, settled edit, partner filing). It starts hidden on mount because nothing persists staleness, it is cleared by the next fully indexed write, and it has no close button. This is narrower than "when no embedding model is configured": a model removed while the roleplayer only reads shows no banner. Record the exact sentence | D11, `007.context.md` |

## `docs/architecture/frontend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| The API client | Add `shared/embeddingFailure.ts`, which maps `no_embedding_model` / `llm_unreachable` to sentences for authoring failures (memo, character, setup). The stream types carry the optional `search_coverage_incomplete` | D10, `008` |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Open `_TBD:` table | Remove the sparse-rowid, archived-fan-out and staleness-marker rows, and list them under "Closed in this pass" | U4, U5, U6 |
| Paths | Add the three new backend modules | D2 |

## Flags for other owners

- **`/product-spec` / architect — `secret_ref_missing` on the degraded path.** U3 lists
  only `no_embedding_model` and `llm_unreachable` as caught. If the designated server's
  `$ENV_VAR` key is unset, a settle or settled edit therefore fails with 500 instead of
  saving degraded. US-112's spirit ("a platform gap never blocks my own record-keeping")
  arguably covers it. Decide whether the degraded path should also catch it.
- **`/product-spec` — banner scope.** US-112.AC-2 is satisfied on the write that degrades.
  Whether the roleplayer should also be told on open, with no write, is not specified. It
  would need a persisted signal, which U5 declined.
- **`fast/002` (rebuild).** It must re-declare the vec0 tables on a dimension change. It
  must back-fill `memo_vec` / `session_vec` for material written before 024 or while
  degraded. It must also rebuild both FTS tables, which is the only repair after a Sync
  rebuild drops their triggers.
- **`025` (querying).** It must not use the forbidden KNN `IN`-pushdown form (D3).

## Observations
