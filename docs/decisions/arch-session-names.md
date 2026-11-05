# Decisions — arch-session-names
**Stage:** — · **Feature:** arch-session-names (architect session, 2026-11-05: sessions gain a roleplayer-given name)

Decisions taken in the /architect session that revised the session-identity
model. The contracts they sit under are stated in the architecture docs cited on
each entry; these entries carry the choice, the reasoning and what was weighed and
rejected. No feature has been planned against them yet — the planner of the
feature that builds session names cites these ids and does not re-decide them.

### DEC-arch-session-names-1 — Name storage: a nullable column, the default label computed by the client
- **Status:** accepted
- **Stage:** — · **Feature:** arch-session-names · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** user
- **Question:** How is a session's name stored, and where does the default label of a never-renamed session (its start date) come from?
- **Decision:** `sessions.name` is a nullable text column; NULL is the default and means "never renamed". The value is trimmed on write and a blank value is stored as NULL. The default label is computed by the client as the **local** `YYYY-MM-DD` of `created_at` and is never stored. Delivered by the drift page's Sync, with no backfill — every existing session reads NULL and shows its date exactly as before.
- **Reason:** The start date depends on the roleplayer's timezone, which only the browser knows; a stored date would be a UTC date that can disagree with the date the roleplayer sees, and would freeze a presentation choice into data. NULL also keeps "renamed" and "never renamed" distinguishable, so clearing a name returns the session to the computed default.
- **Rejected:** Storing the formatted start date at creation — bakes in the server's (UTC) date, makes "never renamed" indistinguishable from "renamed to that date", and needs a backfill of every existing session.
- **Supersedes:** 011 D4 (plan 011's "a session has no title; it is identified by its start time"), a plan-local decision with no DEC id, recorded in the architecture docs only. Product: US-145 is withdrawn and superseded by US-150.
- **Lands in:** `backend/app/db/schema.py` (`sessions.name`); the session response model in `backend/app/models/`; `backend/app/services/sessions.py` (the trim/blank-to-NULL write); a pure label module under `frontend/src/app/` used by every place a session is named
- **Cites:** `data-model.md` § `sessions`; `workspace-shell.md` § the label rule; `frontend-structure.md` § ids are strings (the label derivation bullet); US-150

### DEC-arch-session-names-2 — Route shape: a general `PATCH` that accepts `name` only
- **Status:** accepted
- **Stage:** — · **Feature:** arch-session-names · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** user
- **Question:** What route renames a session — a general `PATCH` on the session resource, or a dedicated name route?
- **Decision:** `PATCH /api/sessions/{session_id}` with body `{ name: string | null }`. `name` is the **only** accepted key; any other key is refused with a 422 (a named exception to the project rule that unknown body keys are ignored). Owner-scoped; a missing or foreign id is `session_not_found` (404); an archived session may be renamed; the answer is 200 with the session. Configuration is still never written through the session resource — it stays on `/api/sessions/{id}/configuration`.
- **Reason:** The user preferred the general resource route as the conventional REST shape. Refusing every other key keeps the original intent of "no PATCH on sessions" — that the session resource never becomes a second, unvalidated path for configuration or lifecycle writes — while allowing the one field that belongs to the session itself.
- **Rejected:** A dedicated `PUT /api/sessions/{session_id}/name` — the architect's recommendation, because a single-purpose route cannot grow into a general session write and needs no exception to the ignore-unknown-keys rule; the user preferred the general route and accepted the strict-body exception as the guard instead. Ignoring unknown keys as elsewhere — rejected because a client sending `model` or `archived_at` would get a silent 200 that did nothing, inviting exactly the drift the old ban prevented.
- **Supersedes:** 017 D9, in part (plan 017's "no `PATCH` and no `DELETE` on sessions") — the `PATCH` half is replaced by this narrow `PATCH`; "no `DELETE`" stands. Plan-local, no DEC id.
- **Lands in:** `backend/app/routers/sessions.py`; the request and response models in `backend/app/models/`; `backend/app/services/sessions.py`; the route-classification enumeration checked by `backend/tests/test_privacy_audit_routes.py` (the new route is an owner route)
- **Cites:** `backend-structure.md` § `/api/sessions` and § request validation; `quick-reference.md` § roleplayer routes; UC-089, US-150

### DEC-arch-session-names-3 — Last-use display: local `YYYY-MM-DD HH:MM`, fixed width
- **Status:** accepted
- **Stage:** — · **Feature:** arch-session-names · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** user
- **Question:** How does the tree row's second line render `last_used_at`?
- **Decision:** As the **local** `YYYY-MM-DD HH:MM`, followed by ` · ` and the setup label. Fixed width, so the second lines of a session list align and the 252px tree row needs no re-measure per row.
- **Reason:** A fixed-width absolute timestamp separates two sessions used on the same day, does not change while the screen sits open, and has a predictable width inside the fixed tree geometry.
- **Rejected:** Relative time ("3 hours ago") — variable width inside a fixed column, and goes stale on screen without a timer. Date only — cannot tell apart two sessions used the same day, which is the common case for a roleplayer running parallel sessions.
- **Lands in:** the pure label module under `frontend/src/app/` (shared with DEC-arch-session-names-1); the tree's session row component under `frontend/src/app/`
- **Cites:** `workspace-shell.md` § the tree row and geometry; US-151

### DEC-arch-session-names-4 — Rename interaction: in-place edit of the label
- **Status:** accepted
- **Stage:** — · **Feature:** arch-session-names · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** architect (default; the planner may refine)
- **Question:** How does the roleplayer rename a session from the tree row and from the session header?
- **Decision:** An `IconEdit` control labelled "Rename session" swaps the label for a single-line in-place editor, pre-filled with the current name (empty when never renamed). Enter or blur commits; Escape cancels and sends nothing; an empty or whitespace-only value sends `null`, returning the session to its date label. The commit is **not optimistic**: the label changes when the server answers, the session lists are re-read and the open header takes the returned session; a failure goes through `notifyFailure` and leaves the old label. Rename is not offered in the character page's Sessions tab.
- **Reason:** One short field in the position of the thing it edits is the in-place reading the project already applies to entries and notes; a modal around one text field is friction with nothing to hold. Never-optimistic is the project rule, and a rename has no reason to be the second exception.
- **Rejected:** A rename modal — a form with one field and no list to protect. `IconPencil` as the glyph — the project already uses `IconEdit` for every edit action, and a second edit glyph would be two icons for one meaning. An optimistic label swap — no stated benefit on a single-instance app that outweighs the rule.
- **Lands in:** the tree's session row and the session header components under `frontend/src/app/`; the sessions client and stores (`frontend/src/app/sessionsApi.ts`, `frontend/src/app/sessionsState.ts`)
- **Cites:** `workspace-shell.md` § rename; `forms-and-lists.md` § the named exceptions and § never optimistic; `ui-conventions.md` § icon table; US-150

### DEC-arch-session-names-5 — My-search's session name arm: `LIKE`, merged ahead of vector hits
- **Status:** accepted
- **Stage:** — · **Feature:** arch-session-names · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** user
- **Question:** How does my-search find a session by its name, given the session corpus is the vector-only port variant?
- **Decision:** A third escaped, case-insensitive, non-tokenised `LIKE` substring match, over `sessions.name`, outside the port, owner-scoped like the other two. In the session group, name hits come first (ordered as the character and setup matches are), then the vector arm's hits with any session already matched by name removed, the group still capped at 20. Name hits carry no fusion score and no snippet. The search still fails whole on a vector-arm error. Hydration returns `name` and `created_at`; results are labelled by the client's label rule. `session_fts` stays uncreated; `session_search` (the assistant's tool) does not read `name`. **Accepted limitation:** a never-renamed session is not found by typing its start date, because that label is computed by the client and never stored.
- **Reason:** A name is one short label per session; an index over it is out of proportion, and the `LIKE` path is already the project's answer for short owner-entered labels (characters, setups). Putting exact name matches first matches what the roleplayer typed the name to find. Matching the date form would need the roleplayer's timezone on the server, which nothing else needs.
- **Rejected:** Creating `session_fts` over `name` — an FTS table, triggers and drift coverage for one short column; flip condition is FTS over `name` alone. Folding `name` into `session_vec`'s embedded text — a re-embed on every rename and a name that blurs semantically. Fusing name hits into the vector ranking by RRF — a substring match has no meaningful rank to fuse. Matching the client-computed date — needs a timezone the server does not have.
- **Lands in:** my-search's service under `backend/app/services/search/`; the search response model in `backend/app/models/`; my-search's results rendering under `frontend/src/app/`
- **Cites:** `search-and-retrieval.md` § three port variants and three `LIKE` matches, § hydration; `quick-reference.md` § search at a glance; defect D-05 (ASCII-only case folding) now covers session names too; US-152

### DEC-arch-session-names-6 — A rename bumps `updated_at` only
- **Status:** accepted
- **Stage:** — · **Feature:** arch-session-names · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** user
- **Question:** Which session timestamps does a rename write?
- **Decision:** `updated_at` only. `last_used_at` is never moved by a rename.
- **Reason:** `last_used_at` orders the tree and characters by newest use; renaming a session is housekeeping, not use, so it must not jump the session to the top — the same reasoning as archive never moving `last_used_at`.
- **Rejected:** Bumping both, as every stream write does — would reorder the tree on a rename, which the roleplayer did not ask for.
- **Lands in:** `backend/app/services/sessions.py`
- **Cites:** `data-model.md` § `sessions` (`last_used_at`); `backend-structure.md` § `/api/sessions`; `domain-rules.md` R6 (archive never moves `last_used_at`, the precedent)

### DEC-arch-session-names-7 — Import accepts `schema_version` 1 through one named upgrade
- **Status:** accepted
- **Stage:** — · **Feature:** arch-session-names · **Step:** —
- **Date:** 2026-11-06 · **Decided by:** user
- **Question:** The `name` column bumps `SCHEMA_VERSION` from 1 to 2, and the importer refuses any `schema_version` inequality (`schema_mismatch`) and any row whose column set differs from the registry (`malformed_payload`). Should version-1 exports still import after the bump?
- **Decision:** Yes, as a named, one-step upgrade. The importer accepts version 2 under the existing rules unchanged, and version 1 with exactly one relaxation: session rows lack `name` and are imported with `name` NULL (never renamed). Every other rule stands — any other version is `schema_mismatch`; a missing or extra column anywhere else is `malformed_payload`; a version-2 session row without `name` is `malformed_payload`.
- **Reason:** Strict equality would make every pre-change export and backup unimportable, including the whole-database restore path. The upgrade is one absent nullable column whose NULL already means "never renamed", so nothing is invented or lost. Naming the version and the column keeps the column-set rule meaningful everywhere else.
- **Rejected:** Keep strict equality — every pre-change export and backup becomes unimportable. A general "missing column imports as NULL" tolerance — would quietly accept truncated or hand-edited files and erode the column-set check for every table.
- **Lands in:** `backend/app/services/transfer_import.py` (the version check and the v1 session-row upgrade beside the existing users-row missing-column allowance); `backend/app/services/transfer.py` (`SCHEMA_VERSION` 1 → 2)
- **Cites:** `transfer.md` § accepted schema versions; flip condition there: a version 3 decides whether the upgrade chain grows or v1 support is dropped
