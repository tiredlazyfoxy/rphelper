# Fast feature 014 — message-delete — context

No `brief.md`, no backlog item. This is the user's own request: "we need the
delete message icon (when I send message twice or something). As well as
message "cleared" fully is to be deleted." The decisions below were confirmed
by the user through the orchestrator on 2026-11-05.

**Requirement:** FEAT-009 (session entries). There is no story for deleting
yet: _TBD: story to be added to FEAT-009 via /product-spec at finalization_.
Related, already-delivered ids that this feature changes: UC-078 / US-110
(editing a settled entry) and US-115 (editing a zone message). Both lose their
"blank commit is a no-op" behaviour. US-116 still holds: a buried row is not
editable, and now not deletable either.

**Docs follow the build.** The user chose to ship now. The missing story and the
architecture changes (a new route, the amended "nothing deletes a message"
rule) are carried in `outcome.md` and applied at `/finalize`. Until then the
architecture contradicts this plan in the places listed there. Where they
conflict, this plan's user-confirmed decisions win.

## What exists today (from the harvest)

Backend:

- `backend/app/routers/stream.py`. The router is
  `APIRouter(tags=["stream"], dependencies=[Depends(require_user)])`.
  `PATCH /api/messages/{message_id}` (`edit_message`, ~265-287) takes
  `message_id: SnowflakeIn`, `current_user`, `connection`, `settings` and
  `client_factory` dependencies and calls `edit_message_text(...,
  client_factory=..., timeout_seconds=settings.llm_request_timeout_seconds)`.
  The new DELETE route mirrors that dependency set. The precedent for a DELETE
  route is `routers/memos.py:180-187` (`delete_own_memo`, 204). This route
  returns 200 instead (decision P2). Module docstring line ~14 says there is no
  delete route; that text is now false.
- `backend/app/errors.py`: `MessageNotFoundError` (404 `message_not_found`, ~452)
  and `MessageNotEditableError` (409 `message_not_editable`, ~435). The global
  handler turns a `DomainError` into `{"error":{"code","message","detail"}}`.
- `backend/app/services/messages.py`: `edit_message_text` (~363) is the template
  for the new service function. Inside `with connection.begin()` it looks up the
  target in the text-free `message_states` selectable (id, user_id, session_id,
  related_to, settled_at), classifies it (not found / buried / settled / zone /
  tool), writes, deletes `translations` rows for the message, then calls
  `refresh_session_vector_degraded(connection, user_id, session_id,
  client_factory=, timeout_seconds=)` (`services/session_index.py:225`, returns
  bool) and `_bump_session(connection, user_id, session_id, now)` (~469).
  `_now_text()` is at ~508. Module docstring lines ~10-13 say nothing deletes a
  message; that text is now false.
- `backend/app/db/schema.py`:
  - `messages` is at ~328-361. `related_to` is an FK to `messages.id`, guarded by
    the `ck_messages_buried_or_settled` constraint.
  - `translations.message_id` (~422-445) is the only other FK to `messages`.
  - No FK has CASCADE, and `PRAGMA foreign_keys=ON` (`db/engine.py:183`).
    Child rows must be deleted before their parent: translations, then buried
    rows, then the target.
  - The selectables are `settled_entries` (~450), `current_zone` (~454),
    `buried_messages` (~461) and `message_states` (~465).
  - The comments at ~324 and ~419-420 say messages are never deleted; that text
    is now false.
- `backend/app/db/search_tables.py`: message FTS is an external-content table.
  Its `message_fts_after_delete` trigger (~96-100) removes the FTS row when a
  record row is deleted, so the service does not clean FTS itself. Comment ~95
  says no delete happens; that text is now false. `session_vec` holds one
  vector per session, built from settled entries. It is refreshed after a
  settled delete, the same way edit does it.
- **FTS ensure precedent.** The memo delete in `services/memos.py:223-239` either
  calls `ensure_fts_tables` before deleting or does not. The coder reads it and
  matches it. If it does, so does `delete_message`, because the delete trigger
  only exists once the FTS tables have been ensured.
- Stream order is `ORDER BY id`. Re-open targets the last settled row. Deleting
  that row makes the previous one the re-open target, which is acceptable.

Frontend:

- `frontend/src/shared/api.ts:180`:
  `apiDelete<T = unknown>(path, signal?)` throws `ApiError` on a non-ok
  response.
- `frontend/src/app/streamApi.ts:147`: `editMessage(id, text, signal)` uses
  `apiPatch` on `/api/messages/${encodeURIComponent(id)}`.
- `frontend/src/app/streamState.ts`:
  - The state fields are `StreamState` (`entries`, `zone`, `kindOverride`,
    `busy`, `searchCoverageIncomplete`, …).
  - Helpers: `isBlank` (~109) and `applyEntries` (~243), which clears
    `kindOverride` when the id sequence changes. The re-reads are
    `rereadEntries` (~287), private `rereadZone` (~304) and `rereadBoth`
    (~323).
  - `editZoneMessage` (~731-769) and `editEntry` (~774). Both currently return
    `true` with no request on blank text (014 D10, 013 D10). The header rule:
    edit effects are never optimistic, never reject, and never set `busy`.
  - `canSettle` and `showsRegenerate` derive from `zone`, so deleting a zone row
    may disable them. That is fine.
- `frontend/src/app/StreamRecord.tsx`: the non-exported `StreamEntry` observer
  (~143-290). Its action `<Group>` (~250-275) holds `IconButton`s: Edit entry,
  PartnerFlicker, Copy as plain text, Re-open last entry. The editor is
  `<Textarea aria-label="Edit entry text" … onBlur={commit}>`, and `commit()`
  calls `editEntry` and then `invalidateTranslation(flicker, entry.id)`.
- `frontend/src/app/ZoneList.tsx`: `ZoneMessage` takes props `{state, message,
  signal?, editable? = true}` with `showsEdit = editable && role !== "tool"`.
  Its header has an "Edit message" `IconButton`. The editor is
  `aria-label="Edit message text"`, and on blur it commits through
  `editZoneMessage`. `DiscussionGroup.tsx:117` reuses `ZoneMessage` with
  `editable={false}`.
- `frontend/src/shared/IconButton.tsx`: props `{icon, label, onClick, disabled?,
  color?, sizeVariant?}`. `label` is both the tooltip and the aria-label.
- `frontend/src/shared/ConfirmModal.tsx`: props `{opened, title, consequence,
  confirmLabel, confirmColor?, loading?, onCancel, onConfirm}`. See
  `src/admin/LlmServersPage.tsx:277-285` for usage. `@mantine/modals` is not
  installed. The convention is in `docs/architecture/forms-and-lists.md`
  (~318-370).
- Precedent for a blank commit that deletes: `src/app/memoLevelState.ts`, where
  blank text calls `deleteMemo` with no confirm.

## User-confirmed decisions (binding)

1. **Docs path.** Build now. The story and the architecture amendments are
   carried in `outcome.md` and applied at finalization. The plan cites the
   requirement as `_TBD: story to be added to FEAT-009 via /product-spec at
   finalization_`.
2. **Scope.** Both settled entries (above the ruler) and individual
   current-zone messages can be deleted, because a double send usually lands
   in the zone.
3. **Buried group.** Deleting a settled head also deletes its buried group (the
   rows whose `related_to` is the head's id), in the same transaction.
4. **Confirm.** The trash icon opens the shared `ConfirmModal` with a red
   confirm button. Committing the editor with blank text deletes immediately,
   with no confirm (memo precedent).

## Planner decisions (this plan)

These are orchestrator defaults, recorded as decisions of this plan.

- **P1 — Refusals mirror edit.**
  - A buried target is refused with `MessageNotEditableError` (409
    `message_not_editable`). So is a `role='tool'` target (mirrors 021 D8).
  - A missing id or another user's id is refused with `MessageNotFoundError`
    (404 `message_not_found`), and the two answers are identical (R5).
  - No new error code.
  - Tool rows get no delete icon. Read-only `ZoneMessage editable={false}`
    (`DiscussionGroup`) gets none either.
  - Rejected: a separate `message_not_deletable` code. A new code would need
    an architecture entry, and the two refusal sets are identical.
- **P2 — Route and response.** The route is `DELETE /api/messages/{message_id}`
  on `routers/stream.py` and returns **200** with a small body: `deleted_ids`
  (string ids) and `search_coverage_incomplete` (bool). The response model is
  `DeleteMessageResponse`, declared beside the stream router's other response
  models.
  - `deleted_ids` order: the target id first, then the buried ids ascending.
  - Rejected: 204, because the vector refresh's coverage flag has to reach the
    client, as it does for settle, reopen and edit.
- **P3 — Service order inside one transaction.** The service function is
  `delete_message` in `services/messages.py`, and it does this:
  1. Classify the target through `message_states`.
  2. Collect the ids to delete: the target, plus its buried group when the
     target is settled.
  3. Delete `translations` rows for all of those ids (scoped to the user).
  4. Delete the buried rows.
  5. Delete the target.
  6. If the target was settled, call `refresh_session_vector_degraded` (same
     arguments as edit). Its result becomes `search_coverage_incomplete`. A
     zone delete reports `false`.
  7. Always call `_bump_session`.

  FTS cleanup is left to the delete trigger, with the ensure precedent above.
- **P4 — Frontend API.** `deleteMessage(id, signal)` in `streamApi.ts` goes
  through `apiDelete` to the same path as `editMessage`.
- **P5 — Effects.** `deleteEntry(state, id, signal)` and
  `deleteZoneMessage(state, id, signal)` in `streamState.ts`, both resolving to
  a boolean.
  - Never optimistic, never reject, never set `busy`.
  - Abort resolves `false` silently, with no notification and no re-read.
  - Failure calls `notifyFailure`, re-reads (entries for `deleteEntry`, the zone
    for `deleteZoneMessage`) and resolves `false`.
  - Success for an entry: remove the row from `entries` through `applyEntries`
    and set `searchCoverageIncomplete` from the response. This resets
    `kindOverride` because the id sequence changed, which is acceptable.
  - Success for a zone message: filter the row out of `state.zone`.
  - Both resolve `true` on success.
- **P6 — Blank commit deletes.** `editEntry` / `editZoneMessage` with blank
  (whitespace-only) text now delegate to `deleteEntry` / `deleteZoneMessage`
  and resolve with their result. This supersedes 014 D10 and 013's zone D10.
  Unchanged text is still a no-op that resolves `true` with no request.
- **P7 — Icon placement and gating.**
  - `IconTrash` with label **"Delete entry"** goes in `StreamEntry`'s action
    row. `IconTrash` with label **"Delete message"** goes in `ZoneMessage`'s
    header, shown only when `editable` is true and the role is not `tool`.
  - Both are disabled while `state.busy` is true, or while a compose stream is
    in flight if `StreamState` tracks that separately from `busy`. This stops
    compose's finalisation re-read from racing a delete.
  - Neither is shown while that row's editor is open.
- **P8 — Confirm dialog wording.**
  - Entry: title "Delete entry?". The consequence says the entry is removed for
    good and, for a settled entry, that its buried discussion goes with it.
  - Zone message: title "Delete message?". The consequence says the message is
    removed for good.
  - Both: `confirmLabel` "Delete", `confirmColor` red, `loading` while the
    request is in flight.
  - Cancel sends nothing. The modal closes once the effect resolves, whatever
    the result.
- **P9 — Stale comments.** Correct the now-false "nothing deletes a message /
  no delete route" comments at `routers/stream.py:14`,
  `services/messages.py:10-13`, `db/schema.py:324` and `:419-420`, and
  `db/search_tables.py:95`. These are code comments and in the coder's scope.

## Test constraints

- Backend pytest runs in parallel, with a 60s per-test limit and no network.
  Embedding is reached through `client_factory`, so tests use the same fake
  embedding factory the existing edit tests use. Settled-delete coverage must
  not need a live embedder.
- Backend helpers already exist:
  - `test_messages_service.py`: `_seed_buried_settled_zone` gives settled head
    11, buried 12 under 11 and zone 13. Also `_seed_user_b_stream`,
    `_insert_message`, `_all_messages` and `_count_messages`.
  - `test_stream_router.py`: `_message_path(id)` and
    `_assert_envelope(response, status, code)`.
- Frontend: `StreamRecordActions.test.tsx` uses a `stubFetch` harness.
  `entryEffects.test.ts` holds a blank-commit test (~254), and
  `streamMutations.test.ts` holds a blank-commit test (~645) plus effect/signal
  tables (~729, ~829). Both blank tests assert the old no-op and must flip.

## Architecture references

- `docs/architecture/session-stream.md`:
  - "The route surface": the route table, plus the "The table is complete … no
    discard route" statement, which this feature amends.
  - "`PATCH /api/messages/{message_id}` — the final reach": the refusal table
    that the delete mirrors.
  - "The degraded embedding path": the coverage flag.
- `docs/architecture/data-model.md`: R6 ("nothing deletes a message"), amended
  by this feature. Also the `messages` / `translations` FKs and the four
  selectables.
- `docs/architecture/forms-and-lists.md`: the confirm convention table.
- `docs/architecture/domain-rules.md`: settle and re-open (~868-885), whose
  re-open target shifts after a settled delete.
- `docs/architecture/backend-structure.md`: the error model (refusal identity)
  and the JSON id boundary (ids are strings on the wire).
