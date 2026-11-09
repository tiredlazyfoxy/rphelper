# Decisions — fast-002.vector-index-rebuild
**Stage:** 004.retrieval · **Feature:** fast/002.vector-index-rebuild

The whole-index rebuild (UC-016) on the admin Database page. The contracts are
`search-and-retrieval.md` "Index rebuild — FEAT-005", `admin-surfaces.md` (the
Database page's page-level actions) and `backend-structure.md` (the admin
database route surface). Written at finalization (2026-11-09) from the feature's
plan-time decisions.

### DEC-F002-1 — One blocking request; no job runner and no progress stream
- **Status:** accepted
- **Stage:** 004.retrieval · **Feature:** fast/002.vector-index-rebuild · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** user
- **Question:** How does the rebuild run — as a background job with progress, or as one request?
- **Decision:** One synchronous `POST /api/admin/database/rebuild` (a sync `def` handler that calls one service function, with no try/except; errors map through the global error model). The page holds the button and the `ConfirmModal` in their loading state until the request returns.
- **Reason:** A rare, confirmed admin operation on a single-user-at-a-time instance does not justify a job runner, a progress channel or a status route.
- **Rejected:** A background job with a progress stream — machinery for one rarely used button.
- **Lands in:** `backend/app/routers/admin_db.py`; `frontend/src/admin/DatabasePage.tsx`; `frontend/src/admin/databasePageState.ts`
- **Cites:** `search-and-retrieval.md` § Index rebuild; `admin-surfaces.md` § the Database page

### DEC-F002-2 — One transaction, all-or-nothing; the write lock is held across embedding
- **Status:** accepted
- **Stage:** 004.retrieval · **Feature:** fast/002.vector-index-rebuild · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** user
- **Question:** What does a failed rebuild leave behind?
- **Decision:** The whole rebuild runs in one transaction. Any failure leaves the previous index — vector rows, vector-table dimensions and FTS contents — exactly as it was. The transaction holds the SQLite write lock across every embedding call, so other writes block for the rebuild's duration; that is accepted.
- **Reason:** A half-rebuilt index is worse than the old one, because nothing records which half is new. The blocking is the price of all-or-nothing on a rare, confirmed operation; it is recorded so nobody "fixes" it into a partial rebuild without knowing what that gives up.
- **Rejected:** Committing per table or per chunk — a failure mid-way would leave a mixed index with no record of which part was rebuilt.
- **Lands in:** `backend/app/services/index_rebuild.py`
- **Cites:** `search-and-retrieval.md` § Index rebuild (operational note); the write-lock flip condition in `search-and-retrieval.md` § The mechanism

### DEC-F002-3 — The response is the fixed list of the four derived table names
- **Status:** accepted
- **Stage:** 004.retrieval · **Feature:** fast/002.vector-index-rebuild · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** user
- **Question:** What may the completion report carry, given the privacy narrowing to "completion and at most counts not derived from user content"?
- **Decision:** 200 `{ tables_rebuilt: [...] }`, always the same four derived table names. Never a memo, session or row count, and never anything per user.
- **Reason:** A count of tables is content-free; any count of rows would be an aggregate over every user's material, which R5 forbids.
- **Lands in:** `backend/app/models/admin_db.py`; `backend/app/services/index_rebuild.py`
- **Cites:** `search-and-retrieval.md` § Index rebuild (the privacy narrowing); `domain-rules.md` R5

### DEC-F002-4 — Always available; no designation fails with `no_embedding_model`
- **Status:** accepted
- **Stage:** 004.retrieval · **Feature:** fast/002.vector-index-rebuild · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** user
- **Question:** Is the Rebuild control gated on drift state or on an embedding designation?
- **Decision:** Neither. The button is never disabled. With no designation the request runs and fails with 409 `no_embedding_model`, shown in the rebuild's own inline red `Alert`, never as a notification.
- **Reason:** The rebuild is the remedy for several states (after a Sync, after a restore, after a designation change); gating it would hide the remedy exactly when it is needed, and the failure message names the missing step.
- **Lands in:** `frontend/src/admin/DatabasePage.tsx`; `frontend/src/admin/databasePageState.ts`
- **Cites:** `admin-surfaces.md` § always available

### DEC-F002-5 — Always drop and re-create both vector tables
- **Status:** accepted
- **Stage:** 004.retrieval · **Feature:** fast/002.vector-index-rebuild · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Step 2 of the designed rebuild re-declared the `vec0` tables only if the dimension had changed. Is that enough?
- **Decision:** Both `vec0` tables are always dropped and re-created at the designated model's `embedding_dim`.
- **Reason:** The rebuild must also clear vectors for rows that no longer exist and vectors from a superseded model at the same dimension. A drop makes "every vector came from this rebuild" true by construction, and it also covers the post-restore state in which the tables are absent.
- **Rejected:** Re-declaring only on a dimension change — leaves orphan and superseded-model vectors in place.
- **Supersedes:** the earlier architecture wording of step 2 ("re-declare the `vec0` tables if `embedding_dim` has changed"), corrected in `search-and-retrieval.md` at this finalization.
- **Lands in:** `backend/app/services/index_rebuild.py`; `backend/app/db/search_tables.py`
- **Cites:** `search-and-retrieval.md` § Index rebuild, step 2

### DEC-F002-6 — Order inside the transaction
- **Status:** accepted
- **Stage:** 004.retrieval · **Feature:** fast/002.vector-index-rebuild · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** In what order do the rebuild's steps run inside the one transaction?
- **Decision:** Validate the designation and open the embedding handle (no network) → drop and re-create the vector tables → embed and write memo vectors → embed and write session vectors → rebuild FTS → return the report.
- **Reason:** The drop takes the write lock first, so no concurrent writer can slip a vector into a table about to be dropped. Validating before any DDL means a missing designation fails before anything is touched.
- **Lands in:** `backend/app/services/index_rebuild.py`

### DEC-F002-7 — Chunked embedding with a fresh handle per chunk
- **Status:** accepted
- **Stage:** 004.retrieval · **Feature:** fast/002.vector-index-rebuild · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** How are every memo and every session embedded without one enormous request?
- **Decision:** In chunks of `REBUILD_EMBED_BATCH_SIZE` = 32 texts, a module-level constant deliberately **not** `Final`, so tests can patch it. Each chunk opens a fresh embedding handle, because a handle is single-use across embed calls. Memo eligibility mirrors the memo write path: a blank body gets no vector.
- **Reason:** One HTTP request for every memo in the instance risks provider payload limits and the request timeout. A patchable constant lets the suite exercise more than one chunk with a handful of rows.
- **Lands in:** `backend/app/services/index_rebuild.py`

### DEC-F002-8 — FTS: full rebuild for memos, record-rows-only refill for messages
- **Status:** accepted
- **Stage:** 004.retrieval · **Feature:** fast/002.vector-index-rebuild · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** How are the two FTS5 indexes rebuilt?
- **Decision:** `memo_fts` uses FTS5's `'rebuild'` command, since its external content is all of `memos.body`. `message_fts` must **not** use `'rebuild'`: its external content table is `messages`, and `'rebuild'` would index zone and buried rows. Instead it is cleared and refilled from record rows only (`settled_at IS NOT NULL AND related_to IS NULL`, the same predicate as its back-fill). Then the FTS triggers are re-issued (`IF NOT EXISTS`), which repairs triggers lost to a Sync rebuild.
- **Reason:** The message index is restricted to settled rows by its triggers, not by its declaration, so a content-table rebuild would break the restriction.
- **Lands in:** `backend/app/db/search_tables.py`; `backend/app/services/index_rebuild.py`
- **Cites:** `data-model.md` § the FTS trigger conditions

### DEC-F002-9 — Placement: a service module, with public table helpers beside their constants
- **Status:** accepted
- **Stage:** 004.retrieval · **Feature:** fast/002.vector-index-rebuild · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Where does the orchestration live, and how does it reach the derived tables' DDL without importing private names?
- **Decision:** A new `services/index_rebuild.py` owns the orchestration. The table-level helpers (drop the vector tables, rebuild the FTS contents) are public functions in `db/search_tables.py`, beside the private constants they need. The service queries memos (id + body) and sessions (id + owning user) directly, because no unscoped lister exists and the owner-scoped session refresh is unsuitable for an all-users loop.
- **Reason:** Keeps the service free of private imports and keeps every derived-table DDL statement in the one module that declares those tables.
- **Lands in:** `backend/app/services/index_rebuild.py`; `backend/app/db/search_tables.py`

### DEC-F002-10 — Page-local confirm state; the confirm button is labelled "Rebuild"
- **Status:** accepted
- **Stage:** 004.retrieval · **Feature:** fast/002.vector-index-rebuild · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Where does the confirm's open state live, and what does its confirm button say?
- **Decision:** The confirm's open flag is page-local view state, not a field of the page store. The `ConfirmModal`'s confirm label is **"Rebuild"**, not "Rebuild index".
- **Reason:** Open/close is view state (`forms-and-lists.md`). The page's own button is already named "Rebuild index"; a confirm button with the same accessible name would make the two indistinguishable by name while the modal is open. The code carries no comment for this, so this entry is the record.
- **Lands in:** `frontend/src/admin/DatabasePage.tsx` (the confirm label constant)
- **Cites:** `forms-and-lists.md` § the confirm convention; `ui-conventions.md` § the accessibility floor
