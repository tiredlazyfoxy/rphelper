# Decisions — fast-005.degraded-embedding-path
**Stage:** 006.repair · **Feature:** fast/005.degraded-embedding-path

The record-keeping writes' degraded embedding path (closes defects D-03 and
D-04). The contracts are `search-and-retrieval.md` "Failure mode, and a
deliberate asymmetry between two write paths" and the owner-scoped-ids rule for
derived stores, mirrored in `backend-structure.md` and `session-stream.md`.
Written at finalization (2026-11-09).

### DEC-F005-1 — The caught set is a named tuple of three errors, not a base type
- **Status:** accepted
- **Stage:** 006.repair · **Feature:** fast/005.degraded-embedding-path · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** How is the degraded path widened to "credentials the instance cannot use" without swallowing bugs?
- **Decision:** `DEGRADED_EMBEDDING_ERRORS` in `services/session_index.py` is a documented module-level tuple of exactly `NoEmbeddingModelError` (including its `dimension_mismatch` form), `LlmUnreachableError` and `SecretRefError`, defined once and used by `refresh_session_vector_degraded`. Any other exception — programming errors, SQL errors, `ValueError`, `RuntimeError` — still propagates and rolls the caller's transaction back. No new exception base is introduced, and `SecretRefError`'s class and its 500 status are unchanged. The strict path catches none of the three.
- **Reason:** A bug in the embedding code must never become "coverage incomplete". `SecretRefError` keeps its 500 because chat uses it too.
- **Rejected:** A common base class for "platform gap" errors — it would make the caught set grow silently with every new subclass. Re-mapping `secret_ref_missing` to another status — changes chat's contract for an embedding fix.
- **Lands in:** `backend/app/services/session_index.py`
- **Cites:** `search-and-retrieval.md` § Failure mode; `backend-structure.md` § the per-code status record

### DEC-F005-2 — A degraded write clears the session's vector, resolving its id owner-scoped first
- **Status:** accepted
- **Stage:** 006.repair · **Feature:** fast/005.degraded-embedding-path · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** What happens to the session's existing `session_vec` row when the degraded path catches?
- **Decision:** It is deleted. The clear first resolves the session id through an owner-scoped `select` on `sessions.id` with a `user_id` predicate, then calls `delete_vector` for what that select returned — the same inline pattern as the strict path's empty-text delete (plan 032 left no reusable helper). The clear is a no-op for an absent table, an absent row, or a session that is not the caller's. Only `session_vec` is cleared: memo writes are fail-hard and never degrade, and FTS is trigger-maintained and ensured before the embedding step. The function's return contract is unchanged (`True` = degraded, `False` = fully refreshed), and nothing records that material is unembedded.
- **Reason:** A stale vector lets `session_search` return a session on text it no longer contains; clearing it drops the session out of semantic search until the whole-index rebuild re-embeds it, which is the accepted consequence. Every embedding-side raise happens before any vector write, so when the wrapper catches, no new vector exists to protect.
- **Supersedes:** 024 U5, second half only ("leave the vector in place"), a plan-local decision with no DEC id. U5's first half — no staleness marker, no staleness column — stands.
- **Lands in:** `backend/app/services/session_index.py`
- **Cites:** `search-and-retrieval.md` § Every write to a derived store resolves its ids through an owner-scoped query; § Failure mode (consequences to hold)
