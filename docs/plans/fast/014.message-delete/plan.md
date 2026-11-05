# Fast feature 014 — message-delete — plan

**Realizes:** FEAT-009. _TBD: story to be added to FEAT-009 via /product-spec at
finalization_. Changes the blank-commit behaviour of UC-078 / US-110 and US-115.

## Goal

Let the roleplayer delete one settled entry (together with its buried
discussion) or one current-zone message. The trash icon asks for confirmation
first. Committing an edit whose text has been cleared deletes the row with no
confirmation.

## Source files

- `backend/app/services/messages.py` — new `delete_message` service function. Module docstring corrected.
- `backend/app/routers/stream.py` — new `DELETE /api/messages/{message_id}` route and its `DeleteMessageResponse` model. Module docstring corrected.
- `backend/app/db/schema.py` — comment-only: the "never deleted" notes at ~324 and ~419-420.
- `backend/app/db/search_tables.py` — comment-only: the no-delete note at ~95.
- `frontend/src/app/streamApi.ts` — new `deleteMessage` call.
- `frontend/src/app/streamState.ts` — new `deleteEntry` and `deleteZoneMessage` effects. `editEntry` and `editZoneMessage` route a blank commit to them.
- `frontend/src/app/StreamRecord.tsx` — "Delete entry" icon and confirm modal in `StreamEntry`.
- `frontend/src/app/ZoneList.tsx` — "Delete message" icon and confirm modal in `ZoneMessage`.

## Test files

- `backend/tests/test_messages_service.py` — modified. Adds `delete_message` service coverage.
- `backend/tests/test_stream_router.py` — modified. Adds DELETE route coverage.
- `frontend/tests/app/entryEffects.test.ts` — modified. Adds `deleteEntry` coverage. The `editEntry` blank-commit test (~254) flips from no-op to delete.
- `frontend/tests/app/streamMutations.test.ts` — modified. Adds `deleteZoneMessage` coverage. The `editZoneMessage` blank-commit test (~645) flips. The effect/signal tables (~729, ~829) gain the new effects where they enumerate effects.
- `frontend/tests/app/StreamRecordActions.test.tsx` — modified. Covers the "Delete entry" icon and its modal.
- `frontend/tests/app/ZoneList.test.tsx` — modified. Covers the "Delete message" icon and its modal, including that it is absent on tool rows and on read-only rows.

## Interface intent

### Backend

- **`delete_message`** (`services/messages.py`) deletes one message the user owns.
  - **Inputs:** a connection, the user id, the message id, and keyword
    `client_factory` and `timeout_seconds` with the same defaults as
    `edit_message_text`.
  - **Output:** a small result carrying `deleted_ids` (the target id first,
    then the buried group's ids ascending; integers inside the backend) and
    `search_coverage_incomplete`.
  - **Refusals:**
    - Missing or foreign id: `MessageNotFoundError`.
    - Buried row: `MessageNotEditableError`.
    - `role='tool'` row: `MessageNotEditableError`.
  - **Work, all in one transaction** (context.md P3):
    1. Delete the translations of every affected id.
    2. Delete the buried group, when the target is settled.
    3. Delete the target.
    4. Refresh the session vector when the target was settled. Its degraded
       result becomes the flag; a zone target gives `false`.
    5. Bump the session.

  A refusal changes nothing.
- **`DELETE /api/messages/{message_id}`** (`routers/stream.py`) takes the same
  dependency set as the PATCH route and calls `delete_message`.
  - **Success:** 200 with a `DeleteMessageResponse` body: `deleted_ids` as
    strings, plus `search_coverage_incomplete`.
  - **Errors:** the standard envelope (404 `message_not_found`, 409
    `message_not_editable`). A malformed id gets the same handling as on PATCH.
  - **Auth:** behind router-level `require_user`.

### Frontend

- **`deleteMessage`** (`streamApi.ts`) takes a message id and an optional abort
  signal and sends the DELETE to `/api/messages/{id}` (id URI-encoded). It
  returns the parsed response body (`deleted_ids` string array and
  `search_coverage_incomplete`) and throws `ApiError` on failure.
- **`deleteEntry`** (`streamState.ts`) takes the stream state, an entry id and
  an optional signal, and resolves to a boolean. It is never optimistic, never
  rejects and never touches `busy`.
  - **Success:** remove the entry from `entries` via `applyEntries`, set
    `searchCoverageIncomplete` from the response, resolve `true`.
  - **Abort:** resolve `false` with no notification and no re-read.
  - **Other failure:** `notifyFailure`, re-read entries, resolve `false`.
- **`deleteZoneMessage`** (`streamState.ts`) has the same shape for a zone
  message.
  - **Success:** filter the row out of `zone`, resolve `true`.
  - **Failure:** `notifyFailure`, re-read the zone, resolve `false`.
- **`editEntry` / `editZoneMessage`** (changed): blank or whitespace-only text
  now delegates to `deleteEntry` / `deleteZoneMessage` and resolves with its
  result. Every other branch is unchanged, including that unchanged text is a
  no-op with no request.
- **`StreamEntry`** (`StreamRecord.tsx, changed`) gains an `IconTrash`
  `IconButton` labelled "Delete entry" in the action row.
  - Hidden while that entry's editor is open.
  - Disabled while the stream is busy or a compose stream is in flight.
  - Clicking it opens `ConfirmModal`: title "Delete entry?", a consequence that
    mentions the buried discussion, confirm label "Delete", red.
  - Confirm calls `deleteEntry`, with the modal `loading` while it runs. Cancel
    closes the modal with no request.
  - A blank commit in the editor goes through `editEntry`, so it deletes with no
    modal.
- **`ZoneMessage`** (`ZoneList.tsx`, changed) gains an `IconTrash`
  `IconButton` labelled "Delete message" in the header.
  - Shown only when `editable` is true and the role is not `tool`, and not while
    the row's editor is open.
  - Disabled under the same condition as the entry icon.
  - The modal has title "Delete message?", confirm label "Delete", red. Confirm
    calls `deleteZoneMessage`.

## Definition of done

Backend service:

- DoD-1 `[test]` Deleting a current-zone message (`role` user or assistant) removes that row and nothing else. The result's `deleted_ids` is exactly that id, and `search_coverage_incomplete` is false.
- DoD-2 `[test]` Deleting a settled head that has a buried group (seed: head 11, buried 12, zone 13) removes 11 and 12 and leaves 13. `deleted_ids` is the head first, then the buried ids ascending.
- DoD-3 `[test]` Deleting a settled entry with no buried group (for example a filed partner block) removes only it.
- DoD-4 `[test]` `translations` rows for every deleted id are removed, and the FK constraints raise no error. Translations of other messages survive.
- DoD-5 `[test]` Deleting a buried row raises `MessageNotEditableError`, and no row (messages or translations) changes.
- DoD-6 `[test]` Deleting a `role='tool'` row raises `MessageNotEditableError`, and nothing changes.
- DoD-7 `[test]` A missing id and another user's id both raise `MessageNotFoundError`, and nothing changes. Another user's stream is never touched by any delete.
- DoD-8 `[test]` A successful delete bumps the owning session's `last_used_at` and `updated_at`. A refused delete does not.
- DoD-9 `[test]` A settled delete refreshes the session vector through the given `client_factory`, and `search_coverage_incomplete` reflects a degraded refresh (true when the embed path degrades). A zone delete does not trigger the refresh.
- DoD-10 `[test]` After deleting a settled entry, a search-index query for its text (the FTS match the existing search tests use) no longer returns it.

Backend route:

- DoD-11 `[test]` `DELETE /api/messages/{id}` on an owned zone or settled message returns 200 with a body holding exactly `deleted_ids` (a list of strings) and `search_coverage_incomplete` (bool). A following GET of entries or zone no longer lists the row.
- DoD-12 `[test]` The DELETE route returns 404 `message_not_found` for a missing id and for another user's id (same envelope), and 409 `message_not_editable` for a buried row and for a tool row.
- DoD-13 `[test]` The DELETE route without a session cookie is refused the same way as the other stream routes.

Frontend effects:

- DoD-14 `[test]` `deleteMessage` sends `DELETE` to `/api/messages/<encoded id>`.
- DoD-15 `[test]` `deleteEntry` success removes the entry from `state.entries`, sets `searchCoverageIncomplete` to the response flag, resolves `true`, and does not set `busy`.
- DoD-16 `[test]` `deleteZoneMessage` success removes the message from `state.zone`, resolves `true`, and does not set `busy`.
- DoD-17 `[test]` On a failing response, `deleteEntry` and `deleteZoneMessage` notify the failure, re-read their list (entries, or zone, respectively), resolve `false`, and never reject.
- DoD-18 `[test]` On abort, both effects resolve `false` with no notification and no re-read.
- DoD-19 `[test]` `editEntry` with blank or whitespace-only text sends the DELETE (not a PATCH) and, on success, removes the entry. `editZoneMessage` does the same for a zone message. The two existing blank-is-no-op tests are updated accordingly.
- DoD-20 `[test]` `editEntry` and `editZoneMessage` with unchanged text still send no request and resolve `true`.

Frontend components:

- DoD-21 `[test]` A stream entry shows a "Delete entry" button. Clicking it opens a confirm dialog and sends no request. Cancel closes the dialog with no request. Confirm sends the DELETE, and the entry disappears.
- DoD-22 `[test]` A zone message (user or assistant) shows a "Delete message" button with the same confirm behaviour. A tool row shows none, and a `ZoneMessage` rendered with `editable={false}` shows none.
- DoD-23 `[test]` Both delete buttons are disabled while `state.busy` is true, and neither is present while that row's editor is open.
- DoD-24 `[test]` Clearing the editor text and blurring (entry and zone) sends the DELETE with no confirm dialog.

Gates and live:

- DoD-25 `[manual/live]` A repo grep of `backend/app` finds no remaining comment that says messages are never deleted or that no delete route exists.
- DoD-26 `[manual/live]` Live: send a message twice and delete the duplicate from the zone. Delete a settled entry that has a discussion group, and its "discussion" affordance goes with it. Clear an entry's text, blur, and it vanishes. The stream and the re-open target behave sanely afterwards.
- DoD-27 `[manual/live]` Gates green: backend `<py> -m pytest`, `<py> -m mypy app`, `<py> -m ruff check .`; frontend `npm test`, `npm run typecheck`, `npm run build`.

## Out of scope

- Deleting a buried row on its own, deleting tool rows, and deleting from the read-only discussion view.
- Undo or soft delete. The delete is permanent.
- Bulk or multi-select delete, and a "clear zone" / discard route.
- Re-ordering, renumbering or re-kinding neighbouring rows after a delete. Settle and re-open semantics are unchanged.
- Invalidating client-side translation caches beyond what the removed row naturally drops.
- Editing `docs/architecture/` or `docs/product/` (carried in `outcome.md`).
