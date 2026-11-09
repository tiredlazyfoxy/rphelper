# Fast feature 014 — message-delete — outcome

Intended documentation changes, applied at finalization.

## Product

- **FEAT-009 — new story (user-confirmed 2026-11-05).** A roleplayer can
  permanently delete a settled entry, or a single message in the current zone,
  after confirming. A settled entry's buried discussion is deleted with it.
  Buried messages and tool records cannot be deleted on their own. Committing an
  edit whose text is fully cleared deletes the entry or message with no
  confirmation. The story is new; give it the next free US id.
- **UC-078 / US-110 and US-115 — delivered with modification.** A blank commit
  of an edit is no longer a no-op. It deletes the entry or message, per the new
  story.

## Architecture

- **`session-stream.md`, "The route surface — FEAT-009 and FEAT-010 in one
  router" (route table).**
  - **Change:** add a route that deletes one message by id. It reports the ids
    removed and the search-coverage flag. Amend "The table is complete … no
    discard route": there is still no discard-the-zone route, but single-message
    delete now exists.
  - **Reason:** user-requested delete of a double send or an unwanted entry.
- **`session-stream.md`, wire-shape paragraph on the coverage flag.**
  - **Change:** the delete response is one more record-keeping write that
    reports the flag in its own response.
  - **Reason:** deleting a settled entry changes the session's indexed text.
- **`session-stream.md`, new subsection beside "`PATCH /api/messages/{message_id}`
  — the final reach".**
  - **Change:** the delete's reach mirrors edit's refusal table:
    - a settled row (and its buried group) or a current-zone row is deletable;
    - a buried row and a tool row are refused as not editable;
    - a missing or foreign id is refused as not found.

    It is one transaction: dependent rows, then the buried group, then the
    target, then the session index refresh for a settled target, then the
    session bump.
  - **Reason:** same classification as edit, stated once.
- **`data-model.md`, R6 ("nothing deletes a message") and the `messages` /
  `translations` notes.**
  - **Change:** amend the rule. Messages are deleted only through the
    single-message delete. A settled head takes its buried group with it, and
    the message's translations are removed in the same transaction.
    Full-text cleanup is the existing after-delete trigger.
  - **Reason:** the rule no longer holds.
- **`search-and-retrieval.md`, embedding lifecycle.**
  - **Change:** deleting a settled entry triggers the same session-vector
    refresh as editing one.
  - **Reason:** the session vector is composed from settled entries.
- **`forms-and-lists.md`, confirm convention table.**
  - **Change:** add "Delete entry / Delete message", with a red confirm. Also
    record the named exception: a blank-commit delete from the inline editor
    has no confirm (the same precedent as memo blank-delete).
  - **Reason:** new destructive action.
- **`workspace-shell.md`, the stream and the current zone.**
  - **Change:** a settled entry's action row and a zone message's header carry a
    delete control (not on tool rows, not in the read-only discussion view). It
    is unavailable while the stream is busy, and a blank editor commit deletes.
  - **Reason:** new UI affordance.
- **`ui-conventions.md`, icon table.**
  - **Change:** add the trash icon for delete entry / delete message.
  - **Reason:** new icon usage.

## Decisions

- User 1: build now; the docs follow at finalization (story `_TBD_` until `/product-spec`).
- User 2: settled entries and individual zone messages are both deletable.
- User 3: deleting a settled head deletes its buried group in the same transaction.
- User 4: the trash icon goes through the shared confirm modal (red). A blank commit deletes with no confirm.
- P1: buried and tool rows are refused with the existing not-editable code, missing or foreign ids with not-found. No new error code.
- P2: `DELETE /api/messages/{message_id}` returns 200 `DeleteMessageResponse` `{deleted_ids, search_coverage_incomplete}`, not 204.
- P3: service order: translations, buried group, target, vector refresh (settled only), session bump. FTS is handled by the trigger.
- P4/P5: frontend `deleteMessage` plus the `deleteEntry` / `deleteZoneMessage` effects. Never optimistic, abort is silent, failure notifies and re-reads.
- P6: a blank edit commit deletes. **Supersedes plan 014 D10 and plan 013 zone D10.**
- P7: the delete icon is hidden on tool rows, on read-only rows and while editing, and disabled while busy or streaming.
- P8: confirm dialog wording ("Delete entry?" / "Delete message?", confirm "Delete", red).
- P9: correct the stale "nothing deletes a message" code comments.

## Observations

_appended by coder / fixer / reviser; each bullet tagged [product] | [architecture] | [decision]_

- [decision] The delete icons are disabled on `state.busy || isStreaming(state)`, because compose never sets `busy` and `composeHandle` is not observable; this mirrors `canSend` / `showsRegenerate`. Possible impact: forms-and-lists / session-stream note on delete gating. Scope: folder frontend/src/app
