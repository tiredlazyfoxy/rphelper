# Feature 034 — session-names — context

## Goal

A session gets a name that the roleplayer can change. A session that has never been renamed shows its local start date. The left tree shows the name on one line and, on a second, smaller line, when the session was last used next to its setup label. Renaming happens in place, from the tree row or from the open session's header. My-search finds a session by its stored name and labels session and entry results with that name.

## Requirements delivered (cite, never restate)

- `docs/product/stories/FEAT-008.rp-sessions.md` — US-150 (AC-1..6). US-145 is withdrawn and superseded by US-150.
- `docs/product/use-cases/FEAT-008.rp-sessions.md` — UC-089.
- `docs/product/stories/FEAT-020.workspace-shell.md` — US-151 (AC-1..2), together with US-088 and US-089, which it builds on.
- `docs/product/stories/FEAT-017.my-search.md` — US-152 (AC-1..2). AC-1 covers **stored names only**. A never-renamed session is not found by typing its date. This is an accepted limitation (DEC-arch-session-names-5); see `outcome.md` `## Product`. Do not build a date search.

## Architecture this feature realizes (read before coding)

- `docs/decisions/arch-session-names.md` — DEC-arch-session-names-1..7. These are binding. This plan refines -4 through DEC-034-11 and DEC-034-13.
- `docs/architecture/data-model.md` § `sessions` — the nullable `name`, and NULL = never renamed.
- `docs/architecture/backend-structure.md` § `/api/sessions` — the `PATCH` table and "Every session payload carries `name`".
- `docs/architecture/transfer.md` § "Session names travel" and § "Accepted schema versions".
- `docs/architecture/search-and-retrieval.md` § "Three port variants and three `LIKE` matches", § "The result shape" (hydration table).
- `docs/architecture/workspace-shell.md` § Geometry (the tree row, the label rule, rename) and § The model picker (the header title row).
- `docs/architecture/forms-and-lists.md` § named exceptions (renaming a session) and § never optimistic / narrowed re-load.
- `docs/architecture/ui-conventions.md` — the icon table (`IconEdit`) and the shared `IconButton`. A bare `ActionIcon` is forbidden.
- `docs/architecture/deployment.md` § Logging — **session names are never logged** at any level. Log the session id instead.
- `docs/architecture/frontend-structure.md` — the MobX rules (data classes with observable fields only, free-function effects, `runInAction`, abort-aware) and "ids are strings".

## Decisions this plan rests on

`docs/decisions/034.session-names.md`, DEC-034-1..14. Steps cite them by id and do not restate them.

## Cross-cutting facts (used by 2+ steps)

- **Wire shape of a session.** Every session payload (lists, single read, archive and restore, start, create-and-seed, the rename answer) carries `name`: a string, or null when never renamed. The server never computes the default label.
- **Label vocabulary.** *name* is the stored value, possibly null. The *label* is name, or the local `YYYY-MM-DD` of `created_at` when the name is null (one client derivation, `frontend/src/app/sessionLabel.ts`). *Last use* is `last_used_at`, rendered as local `YYYY-MM-DD HH:MM`.
- **A rename writes `name` and `updated_at` only.** It never writes `last_used_at` (DEC-arch-session-names-6), so no list order changes.
- **Never optimistic.** A label changes only once the server has answered (forms-and-lists.md).
- **Privacy.** `sessions.name` is user content. It is owner-scoped on every read, it is a sentinel carrier in the privacy audit (DEC-034-4), and it never appears in a log line.

## Working rules for every downstream agent

- **Read the folder `CLAUDE.md` glossaries first**: `backend/app/*/CLAUDE.md`, `frontend/src/app/CLAUDE.md`, and the tests folders' files where present. They are the map of the code. The harvests behind this plan are `docs/.cache/harvests/034.session-names.backend.md` and `docs/.cache/harvests/034.session-names.frontend.md`.
- Commands come from the root `CLAUDE.md` only.
- **The working tree carries unrelated uncommitted changes**: fast/014–016 and a plan-019 fix. They touch, among others, `backend/app/db/schema.py`, `backend/app/services/messages.py`, `backend/tests/privacy_audit_support.py`, `backend/tests/test_privacy_audit_*.py`, `backend/tests/test_stream_router.py`, `backend/tests/test_messages_service.py` and several `frontend/tests/app/*` files. Preserve those edits and build on top of them. Never revert, re-stage or depend on them beyond what is already in the file.
- Existing tests that assert exact key sets or construct `Session` / `RpSession` / `SessionHit` values belong to the step that changes the shape. Each step's Test files list names them.
