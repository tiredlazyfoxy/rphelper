# fast/005.degraded-embedding-path — context

**Delivers:** FEAT-009 — US-112.AC-1 (the widened half: credentials cannot be
used) and US-112.AC-3. US-112.AC-2 is already delivered by `024` and must keep
holding.
**Closes:** defects D-03 and D-04 (`docs/plans/defects.md`;
`docs/architecture/search-and-retrieval.md` "Two defects live on the degraded
path").
**Depends on:** `024.embedding-lifecycle` (built the degraded path) and
`032.privacy-isolation-audit` (the owner-scoped-ids rule for derived stores).

## Files involved

| Path | Role here |
|---|---|
| `backend/app/services/session_index.py` | The only file that changes. It holds `refresh_session_vector_degraded`, the single degraded function, and the strict `refresh_session_vectors` it wraps. |
| `backend/app/services/embedding.py` | Read-only. Provides `delete_vector(connection, table_name, row_id)`, which takes no user id and is a no-op when the table is absent. It also provides `SESSION_VEC_TABLE`. |
| `backend/app/errors.py` | Read-only. `NoEmbeddingModelError` (409), `LlmUnreachableError` (502) and `SecretRefError` (500, `secret_ref_missing`). |
| `backend/app/secrets.py` | Read-only. `resolve_secret` raises `SecretRefError` for an unset `$VAR` or a malformed ref. The embedding side reaches it through `open_embedding_model`. |
| `backend/app/services/settle.py`, `backend/app/services/messages.py` | Read-only callers: settle (~127), re-open (~206), partner filing (~342) and settled-entry edit (~430). Each stores the returned bool as `search_coverage_incomplete`, and the routers copy it to the wire. They do not change. |
| `backend/tests/test_session_index.py` | Unit tests for the degraded path (~610-720). `~610` pins "keeps the stale vector", which is the old contract. |
| `backend/tests/test_record_keeping_embedding.py` | Router-level record-keeping tests (~531-820). `~583` pins "leaves a stale vector byte-identical", which is the old contract. It has helpers `_seed_designation`, `_preexisting_vector`, `_stored_blob` and `_vector_row_count`. |
| `backend/tests/llm_fakes.py` | Read-only for this feature. It provides `FakeClientFactory`. |

## How the code behaves today (from the harvest)

- `refresh_session_vector_degraded` wraps
  `refresh_session_vectors(connection, user_id, (session_id,), ...)`. It catches
  exactly `(NoEmbeddingModelError, LlmUnreachableError)` and returns `True`.
  Everything else propagates, including `SecretRefError`, which produces the
  500 (D-03). On a catch it leaves the existing `session_vec` row untouched,
  which produces the stale vector (D-04). It returns `False` when nothing was
  degraded.
- The strict function runs in this order:
  1. `ensure_fts_tables`
  2. compose the text
  3. owner-scoped delete of the vectors of sessions whose text is empty
  4. `open_embedding_model`
  5. `ensure_vector_tables`
  6. `embed_texts`
  7. `write_vector`

  Every embedding-side raise happens before any vector write. So when the
  degraded wrapper catches, no new vector has been written for the session.
- Everything runs inside the caller's single transaction. A catch must leave
  that transaction usable so that the relational write commits.
- FTS is trigger-maintained and is ensured before the embedding step, so it is
  unaffected by this feature.

## Constraints (binding)

1. **The strict path does not change.** This covers `refresh_session_vectors`
   itself, the memo write path (`_refresh_memo_search_rows`, which catches
   nothing), the persona and setup fan-outs, `index_rebuild.py` and the whole
   query side. With an unset key, all of these still fail loudly.
2. **The caught set is a named set, not a base type.** It is exactly
   `NoEmbeddingModelError`, `LlmUnreachableError` and `SecretRefError`. It is
   defined once, as a documented module-level tuple constant in
   `session_index.py`. Any other exception still propagates and rolls the
   caller's transaction back: programming errors, SQL errors, `ValueError`,
   `RuntimeError` and so on. A bug in the embedding code must never become
   "coverage incomplete". No new exception base is introduced. `SecretRefError`'s
   class and its 500 status are not changed, because chat also uses it.
3. **Owner-scoped derived-store writes** (032; `search-and-retrieval.md`, "Every
   write to a derived store resolves its ids through an owner-scoped query").
   `vec0` has no user column and `delete_vector` takes no user id. So the clear
   must first resolve the session id through an owner-scoped `select` on
   `sessions.id` with a `user_id` predicate. It deletes only what that select
   returns. 032 left no reusable helper: the pattern is the inline owner-scoped
   select already used in `refresh_session_vectors`' empty-text delete. Mirror
   that pattern.
4. **The clear is a no-op when there is nothing to clear.** That covers an
   absent `session_vec` table, an absent row, and a session that is not the
   caller's.
5. **Nothing records that material is unembedded** (`024` U5, first half,
   upheld). There is no staleness column and no marker. A cleared session simply
   drops out of semantic search until the whole-index rebuild (`fast/002`,
   UC-016) re-embeds it. `docs/product/features.md` records this as an accepted
   consequence (finalization 2026-10-06): "Material whose embedding could not be
   produced has its vectors cleared…".
6. **US-112.AC-3 reverses only U5's second half.** U5 said "leave the vector in
   place"; the new rule is "clear it". The function's return contract does not
   change: `True` means degraded and `False` means fully refreshed.

## Not backed by code — deliberately excluded

The brief says "material", which could be read as covering memos. Memo writes
are **not** degraded today. They are fail-hard by design (the authoring-act
asymmetry in `search-and-retrieval.md`). Only `session_vec` has a degraded
path, so only `session_vec` is cleared.
