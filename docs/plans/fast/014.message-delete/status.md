# Fast feature 014 — message-delete

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-11-05 |

## Files Changed

- `backend/app/services/messages.py` — `delete_message` body (one transaction: translations, buried group, target, FTS ensure, settled-only vector refresh, session bump); module docstring corrected
- `backend/app/routers/stream.py` — `delete_own_message` body calling `delete_message`; module docstring corrected
- `backend/app/models/stream.py` — `DeleteMessageResponse` (skeleton-placed; unchanged by the coder)
- `backend/app/db/schema.py` — comment-only: `messages` and `translations` FK notes no longer say nothing deletes a message
- `backend/app/db/search_tables.py` — comment-only: the message FTS delete trigger note
- `frontend/src/app/streamApi.ts` — `deleteMessage` body via `apiDelete`; header comment
- `frontend/src/app/streamState.ts` — `deleteEntry` / `deleteZoneMessage` effects; blank commit in `editEntry` / `editZoneMessage` delegates to them
- `frontend/src/app/StreamRecord.tsx` — "Delete entry" `IconTrash` button and `ConfirmModal` in `StreamEntry`
- `frontend/src/app/ZoneList.tsx` — "Delete message" `IconTrash` button and `ConfirmModal` in `ZoneMessage` (editable non-tool rows only)

## Skeleton

### Frozen interface (2026-11-05)
- `backend/app/services/messages.py` — `@dataclass(frozen=True) class DeleteMessageResult: deleted_ids: list[int]; search_coverage_incomplete: bool` — new
- `backend/app/services/messages.py` — `delete_message(connection: Connection, user_id: int, message_id: int, *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> DeleteMessageResult` — new (raises `NotImplementedError`)
- `backend/app/models/stream.py` — `class DeleteMessageResponse(BaseModel): deleted_ids: list[SnowflakeOut]; search_coverage_incomplete: bool` — new. **Placed beside `MessageResponse` in `app/models/stream.py`, not in `routers/stream.py` as the plan's Source files say** (the router declares no models; it imports them from here).
- `backend/app/routers/stream.py` — `@router.delete("/api/messages/{message_id}", status_code=200) def delete_own_message(message_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)], settings: Annotated[Settings, Depends(get_settings)], client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)]) -> DeleteMessageResponse` — new (raises `NotImplementedError`). `DeleteMessageResponse` imported; `delete_message` deliberately **not** imported yet (ruff F401) — the coder adds it.
- `frontend/src/app/streamApi.ts` — `export type DeleteMessageResult = { deleted_ids: string[]; search_coverage_incomplete: boolean }` — new
- `frontend/src/app/streamApi.ts` — `export async function deleteMessage(messageId: string, signal?: AbortSignal): Promise<DeleteMessageResult>` — new (throws); `apiDelete` added to the `../shared/api` import.
- `frontend/src/app/streamState.ts` — `export async function deleteEntry(state: StreamState, messageId: string, signal?: AbortSignal): Promise<boolean>` — new (throws)
- `frontend/src/app/streamState.ts` — `export async function deleteZoneMessage(state: StreamState, messageId: string, signal?: AbortSignal): Promise<boolean>` — new (throws)
- `frontend/src/app/streamState.ts` — `editEntry(state, messageId, text, signal?) -> Promise<boolean>` and `editZoneMessage(state, messageId, text, signal?) -> Promise<boolean>` — signatures unchanged; the blank-text branch now throws `not implemented` (was `return true`), every other branch preserved.
- `frontend/src/app/StreamRecord.tsx` (`StreamEntry`), `frontend/src/app/ZoneList.tsx` (`ZoneMessage`) — no signature/prop change; the trash icons and `ConfirmModal`s are behaviour for the coder.
- Caller-compile edits (out of Source-files scope): `backend/app/models/stream.py` — new `DeleteMessageResponse` model appended (see above). Otherwise none.
- Gates at freeze: `mypy app` clean, `ruff check .` clean, `npm run typecheck` clean.

## Tests

### Tests (2026-11-05)
- `backend/tests/test_messages_service.py` — covers DoD-1..DoD-10 (`__F014_DoD<n>`) — `delete_message`: zone row removed alone (flag false); settled head takes buried group, `deleted_ids` head-first then buried ascending; lone partner block; translations of every deleted id cleared, others survive; buried / tool → `MessageNotEditableError`, foreign / unknown → `MessageNotFoundError`, all with messages + translations + sessions unchanged; success bumps session, refusal does not; settled refresh via fake factory (model → flag false and survivor-only embed text; no model / unreachable → flag true), zone delete builds no client; `message_fts` MATCH no longer finds the deleted entry. **Amended** 012 DoD-13's "no delete path" guard → `test_the_module_deletes_only_messages_and_translations__S012_002_DoD13__F014_DoD4` (deletes may target `messages` and `translations` only; no aliased `delete`; no raw `DELETE` inside `text(...)` — the whole-source keyword scan was dropped because the corrected module docstring may name the DELETE route).
- `backend/tests/test_stream_router.py` — covers DoD-11..DoD-13 — DELETE 200 with exactly `{deleted_ids: [str], search_coverage_incomplete: bool}` for zone / settled head (+ buried) / partner, follow-up GET no longer lists the row; 404 `message_not_found` for unknown and B's ids (identical body), 409 `message_not_editable` for buried and raw-seeded tool row, 422 for a non-numeric id; anonymous → 401 same envelope as PATCH. **Amended** 012 DoD-17: route-surface guard now exempts (and requires) DELETE on `/api/messages/{message_id}`; the "DELETE answers 405" test was removed (contradicts the plan).
- `frontend/tests/app/entryEffects.test.ts` — covers DoD-14, DoD-15, DoD-17, DoD-18, DoD-19, DoD-20 — `deleteMessage` DELETE path (URI-encoded), parsed body, `ApiError` on failure; `deleteEntry` success / failure (re-reads entries) / abort (no re-read, no notify), never busy, not optimistic; `editEntry` blank → DELETE (flipped from 014 step 004's DoD-4 no-op), unchanged → no request.
- `frontend/tests/app/streamMutations.test.ts` — covers DoD-16, DoD-17, DoD-18, DoD-19, DoD-20 — `deleteZoneMessage` success / failure (re-reads zone) / abort; `editZoneMessage` blank → DELETE (flipped from 013 DoD-13 no-op), unchanged → no request; `deleteZoneMessage`, `deleteEntry` and blank `editZoneMessage` added to the "every effect and its signal" and "success paths never notify" tables.
- `frontend/tests/app/StreamRecordActions.test.tsx` — covers DoD-21, DoD-23, DoD-24 — "Delete entry" on every kind; dialog "Delete entry?" / "Delete"; cancel → no request; confirm → DELETE and entry gone; disabled while busy; absent while that entry's editor is open; whitespace / empty commit deletes with no dialog (flipped from 014 step 005 DoD-6).
- `frontend/tests/app/ZoneList.test.tsx` — covers DoD-22, DoD-23, DoD-24 — "Delete message" on user + assistant rows, none on tool rows or `ZoneMessage editable={false}`; dialog "Delete message?" / "Delete"; cancel / confirm; disabled while busy; absent while editor open; whitespace / empty commit deletes with no dialog (flipped from 013 step 005 DoD-4).
- Red-gate re-route (TEST fault, 2026-11-05) — privacy-audit route enumeration, DoD-11 / DoD-12: `backend/tests/privacy_audit_support.py` gains row 75 `DELETE /api/messages/{}` classed `owner` / `message_not_found`, the same as row 45 (PATCH on the same path). Every count and table built on that enumeration moves with it: `backend/tests/test_privacy_audit_routes.py` (`EXPECTED_ROW_COUNT` 74 → 75); `backend/tests/test_privacy_audit_owner_sweep.py` (`EXPECTED_OWNER_ROWS` 35 → 36, row 75 declared bodyless, so it gets the same B's-id → 404 refusal-identity probe as PATCH); `backend/tests/test_privacy_audit_logs.py` (swept rows 48 → 49, owner rows 35 → 36; the success-path driver deletes a throwaway zone message of A's as row 75, and the refusal sweep drives row 75 with B's id).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓, DoD-17 ✓, DoD-18 ✓, DoD-19 ✓, DoD-20 ✓, DoD-21 ✓, DoD-22 ✓, DoD-23 ✓, DoD-24 ✓, DoD-25 [manual/live, no test], DoD-26 [manual/live, no test], DoD-27 [manual/live, no test]
- Not asserted: the "compose stream in flight" half of P7's disable rule (conditional in the plan — "if `StreamState` tracks that separately"); DoD-23 is covered through `state.busy` only.

## Notes & Issues

- `ruff check .` from `backend/` reports F402 (loop variable `text` shadows the `sqlalchemy.text` import) at `backend/tests/test_messages_service.py:1299` in `_seed_weeks_old_turn`, a test file outside the coder's scope; `ruff check app` and `mypy app` are clean.
- The FTS ensure follows `memos.delete_memo`: `ensure_fts_tables` runs inside the transaction after the deletes (the trigger handles an existing index; a never-built index is back-filled from the remaining rows).
