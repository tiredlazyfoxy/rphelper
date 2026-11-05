# Decisions — fast-014.message-delete
**Stage:** — · **Feature:** fast/014.message-delete

Single-message delete: `DELETE /api/messages/{message_id}` and its two client
controls (US-149). The contract is in `session-stream.md` ("`DELETE
/api/messages/{message_id}` — the reach"), `domain-rules.md` R6 / R7 / R11 and
`workspace-shell.md`; the entries below record the choices made inside it.

### DEC-F014-1 — Build single-message delete now; the docs follow at finalization
- **Status:** accepted
- **Stage:** — · **Feature:** fast/014.message-delete · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** user
- **Question:** R11 as written allowed only two raw-`messages` operations (settle and re-open). Should the architecture be revised before the delete is built, or should it be built and the docs follow?
- **Decision:** Build now. The architecture and product docs are brought in line at this feature's finalization: R11 becomes three operations, and the ban on a zone-discard route stays.
- **Reason:** User decision. Finalization is where each layer is reconciled with what shipped, so the docs land once, matching the build.
- **Lands in:** `docs/architecture/domain-rules.md` R11, `session-stream.md`, `workspace-shell.md` (at finalization)
- **Cites:** `domain-rules.md` R11

### DEC-F014-2 — Settled entries and current-zone messages are both deletable
- **Status:** accepted
- **Stage:** — · **Feature:** fast/014.message-delete · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** user
- **Question:** Which rows may the roleplayer delete: only zone messages, only settled entries, or both?
- **Decision:** Both. Any settled entry of any kind, and any current-zone message, the user's or the assistant's. Buried and tool rows are refused (DEC-F014-5).
- **Reason:** User decision. Delete reaches the same rows edit reaches, so one classification serves both routes.
- **Lands in:** `backend/app/services/messages.py` (`delete_message`)
- **Cites:** `session-stream.md` "`DELETE /api/messages/{message_id}` — the reach"; US-149

### DEC-F014-3 — A settled head takes its buried group with it, in the same transaction
- **Status:** accepted
- **Stage:** — · **Feature:** fast/014.message-delete · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** user
- **Question:** When a settled entry with a buried discussion is deleted, what happens to the buried rows?
- **Decision:** They are deleted with it, in the same transaction. A buried row cannot be deleted on its own; it leaves only with its head.
- **Reason:** User decision. A buried group has no meaning without its head and no remaining access path (the discussion read is addressed through the head), so leaving it behind would create unreachable rows.
- **Lands in:** `backend/app/services/messages.py` (`delete_message`)
- **Cites:** `domain-rules.md` R7, R11; `data-model.md` Decision history 2026-11-05

### DEC-F014-4 — The trash control confirms in red; a blank editor commit does not
- **Status:** accepted
- **Stage:** — · **Feature:** fast/014.message-delete · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** user
- **Question:** Does delete need a confirmation step, and on which path?
- **Decision:** The trash control opens the shared confirm modal with a red confirm. Emptying the in-place editor and committing deletes with no confirm, the same as a note.
- **Reason:** User decision. The confirm guards the one-click control, where a misclick is the risk. Clearing the text and leaving the field is already a deliberate two-step act.
- **Lands in:** `frontend/src/app/StreamRecord.tsx`, `frontend/src/app/ZoneList.tsx`
- **Cites:** `forms-and-lists.md` "The confirm convention"; `workspace-shell.md`

### DEC-F014-5 — Delete refusals mirror edit's — no new error code
- **Status:** accepted
- **Stage:** — · **Feature:** fast/014.message-delete · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** planner
- **Question:** How does the delete route refuse a buried row, a tool row, and a missing or foreign id?
- **Decision:** It uses the same codes as `PATCH`: `message_not_editable` (409) for a buried or `role='tool'` row, and `message_not_found` (404) for a missing or foreign id, with the two 404s identical.
- **Reason:** The refusal set is exactly edit's, so a second code would carry the same meaning under a different name, and the two tables could drift.
- **Rejected:** A new `message_not_deletable` code, which would have an identical refusal set.
- **Lands in:** `backend/app/services/messages.py` (`delete_message`), `backend/app/routers/stream.py` (`delete_own_message`)
- **Cites:** `session-stream.md` "`DELETE /api/messages/{message_id}` — the reach"; `domain-rules.md` R5, R7

### DEC-F014-6 — 200 with `{deleted_ids, search_coverage_incomplete}`, not 204
- **Status:** accepted
- **Stage:** — · **Feature:** fast/014.message-delete · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** planner
- **Question:** What does a successful delete answer?
- **Decision:** 200 with `{ deleted_ids, search_coverage_incomplete }`. `deleted_ids` lists the target's id first, then the buried ids ascending, as decimal strings. The flag is `false` for a zone delete.
- **Reason:** Deleting a settled entry changes the session's indexed text, so the coverage flag must reach the client as it does on every record-keeping write. The ids let the client remove exactly what went without re-reading.
- **Rejected:** 204 No Content (the memo delete's shape), which cannot carry the coverage flag.
- **Lands in:** `backend/app/models/stream.py` (`DeleteMessageResponse`), `backend/app/routers/stream.py` (`delete_own_message`)
- **Cites:** `session-stream.md` wire shape; `search-and-retrieval.md` degraded write path

### DEC-F014-7 — The service's order inside one transaction
- **Status:** accepted
- **Stage:** — · **Feature:** fast/014.message-delete · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** planner
- **Question:** In what order does the delete touch `messages` and its dependants?
- **Decision:** One transaction, in this order:
  1. classify the target through `message_states`, owner-scoped
  2. delete the affected ids' `translations` rows
  3. delete the buried group (settled target only)
  4. delete the target
  5. full-text upkeep (DEC-F014-8)
  6. refresh `session_vec` (settled target only, degraded path)
  7. bump the session's `last_used_at` and `updated_at`
- **Reason:** No foreign key on `messages` cascades, so dependants go before what they reference. Classifying through the text-free selectable keeps raw-`messages` reads inside the three permitted operations and is the same classification `PATCH` uses.
- **Lands in:** `backend/app/services/messages.py` (`delete_message`)
- **Cites:** `session-stream.md` "One transaction, in an order the schema forces"; `domain-rules.md` R11

### DEC-F014-8 — Full-text upkeep follows the memo delete's placement
- **Status:** accepted
- **Stage:** — · **Feature:** fast/014.message-delete · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** planner
- **Question:** Where does the delete keep `message_fts` correct?
- **Decision:** It follows `memos.delete_memo`: the full-text ensure runs inside the transaction after the deletes; the after-delete trigger removes the index entries of the deleted record rows; the service writes no full-text row itself; and an index that was never built is back-filled by the ensure.
- **Reason:** It reuses the one existing delete-path precedent, so trigger ownership of the index stays uniform.
- **Lands in:** `backend/app/services/messages.py` (`delete_message`), `backend/app/db/search_tables.py`
- **Cites:** `search-and-retrieval.md` trigger conditions; `data-model.md` FTS5 tables

### DEC-F014-9 — Frontend delete effects: never optimistic, never rejecting, never setting busy
- **Status:** accepted
- **Stage:** — · **Feature:** fast/014.message-delete · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** planner
- **Question:** How does the client issue a delete and apply its result?
- **Decision:**
  - One API call, `deleteMessage`, with two effects, `deleteEntry` (settled) and `deleteZoneMessage` (zone).
  - Neither effect is optimistic, rejects, or sets `busy`.
  - An abort is silent.
  - A failure goes through `notifyFailure`, then re-reads.
  - Success removes the named rows only after the server answers and takes the coverage flag from the response. Entries are removed through `applyEntries`, which also resets the kind switch's `kindOverride`.
- **Reason:** This is the workspace's never-optimistic rule in its narrowed form, as an edit replaces one row from its response. Removing only the rows the server names cannot diverge from the server.
- **Lands in:** `frontend/src/app/streamApi.ts`, `frontend/src/app/streamState.ts`
- **Cites:** `forms-and-lists.md` "Mutations are never optimistic"

### DEC-F014-10 — A blank edit commit delegates to delete; unchanged text is a no-op
- **Status:** accepted
- **Stage:** — · **Feature:** fast/014.message-delete · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** planner
- **Question:** What does committing the in-place editor do when the text is blank, or unchanged?
- **Decision:** Blank (after trimming) → the delete effect for that row, with no confirm and no `PATCH`. Unchanged → nothing is sent. `PATCH` never deletes.
- **Reason:** The editor then behaves like the note editor, and one server operation owns removal.
- **Supersedes:** plan 014 D10 and plan 013's zone D10. Both are plan-local decisions with no DEC id, and both governed the blank commit before this feature.
- **Lands in:** `frontend/src/app/StreamRecord.tsx`, `frontend/src/app/ZoneList.tsx`, `frontend/src/app/streamState.ts`
- **Cites:** `workspace-shell.md` blur rule; `session-stream.md` "PATCH never deletes"

### DEC-F014-11 — Trash icon placement, labels and gating
- **Status:** accepted
- **Stage:** — · **Feature:** fast/014.message-delete · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** planner
- **Question:** Where does the delete control sit, what is it called, and when is it present?
- **Decision:**
  - `IconTrash` through the shared `IconButton`, in the entry's revealed action group beside edit.
  - Labelled "Delete entry" on a settled entry and "Delete message" in the zone, following edit's naming split.
  - Absent on tool rows, in the read-only discussion view, and while that row's editor is open.
  - Disabled while busy or streaming (DEC-F014-13).
- **Reason:** It mirrors edit's placement and naming so the two controls read as a pair. Hiding it while editing leaves the blank commit as the one delete path inside the editor.
- **Lands in:** `frontend/src/app/StreamRecord.tsx`, `frontend/src/app/ZoneList.tsx`
- **Cites:** `ui-conventions.md` icon table; `workspace-shell.md` "Deleting an entry"

### DEC-F014-12 — What single-message delete deliberately does not do
- **Status:** accepted
- **Stage:** — · **Feature:** fast/014.message-delete · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** planner
- **Question:** What is out of scope, so it is not added later as an assumed gap?
- **Decision:** None of the following:
  - deleting a buried or tool row on its own
  - deleting from the read-only discussion view
  - undo or soft delete
  - bulk delete or a clear-zone route
  - reordering, re-kinding or re-numbering neighbours
  - translation-cache invalidation beyond the deleted rows' own
- **Reason:** Each would widen R11 past one addressed message, or add state the product does not ask for. The zone-discard ban stands.
- **Lands in:** —
- **Cites:** `domain-rules.md` R11; `quick-reference.md` Deferred / non-goals

### DEC-F014-13 — The trash control's disabled condition, and its untested half
- **Status:** accepted
- **Stage:** — · **Feature:** fast/014.message-delete · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** coder (confirmed: user)
- **Question:** When is the trash control disabled, given that compose never sets `busy`?
- **Decision:** It is disabled on `state.busy || isStreaming(state)`, mirroring `canSend` and `showsRegenerate`. Compose never sets `busy`, and `composeHandle` is not observable, so `isStreaming` is the streaming half of the condition.
- **Reason:** It reuses the derivation the composer already trusts, rather than a third notion of "a mutation is in flight". Recorded as a caveat: the plan's DoD-23 covers only the `busy` half, and the `isStreaming` half has no test.
- **Lands in:** `frontend/src/app/StreamRecord.tsx`, `frontend/src/app/ZoneList.tsx`, `frontend/src/app/streamState.ts`
- **Cites:** `workspace-shell.md` "Deleting an entry"
