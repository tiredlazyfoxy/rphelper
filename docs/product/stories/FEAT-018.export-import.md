<!-- product-spec:start -->
# FEAT-018 — Export & import — stories

### US-077 — Admin exports the whole database
- **Actor:** ACT-001 · **Feature:** FEAT-018 · **Exercises:** UC-061
- **Story:** As an administrator, I want to export and import the whole database, so that I can move or restore an instance.
- **Acceptance criteria:**
  - **US-077.AC-1** — Given the administrator is authenticated, when they request a whole-database export, then the instance produces the export file.
  - **US-077.AC-2** — Given a whole-database export is imported, when the import completes, then every user's data is restored as it was.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2.

### US-078 — The administrator can read no user content anywhere in the product
- **Actor:** ACT-001 · **Feature:** FEAT-018 · **Exercises:** UC-061
- **Story:** As an administrator, I want the whole-database export to give me no way to read user content, so that I can move data without becoming able to see it.
- **Acceptance criteria:**
  - **US-078.AC-1** — Given the administrator has produced a whole-database export, when they attempt to view its contents through the product, then no viewer is offered.
  - **US-078.AC-2** — Given the administrator has produced a whole-database export, when they attempt to search its contents through the product, then no search is offered.
  - **US-078.AC-3** — Given the administrator has produced a whole-database export, when they attempt to render its contents through the product, then no rendering is offered.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2, challenge C1.

### US-079 — A user exports their own data with memos
- **Actor:** ACT-002 · **Feature:** FEAT-018 · **Exercises:** UC-062
- **Story:** As a roleplayer, I want to export and import my own user data with memos, so that I can back up or move everything I own.
- **Acceptance criteria:**
  - **US-079.AC-1** — Given the roleplayer requests an export of their own data, when it is produced, then it includes the roleplayer's memos.
  - **US-079.AC-2** — Given the roleplayer imports their own exported data, when the import completes, then their characters, setups, sessions and memos are restored.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2.

### US-080 — Character export and import
- **Actor:** ACT-002 · **Feature:** FEAT-018 · **Exercises:** UC-063
- **Story:** As a roleplayer, I want to export and import a single character with its memos, so that I can move or share just that character.
- **Acceptance criteria:**
  - **US-080.AC-1** — Given the roleplayer selects a character to export, when it is produced, then the export includes the character's own memos.
  - **US-080.AC-2** — Given the roleplayer imports a character export, when the import completes, then the character and its memos are restored.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2.

### US-081 — A session export carries only its own memos
- **Actor:** ACT-002 · **Feature:** FEAT-018 · **Exercises:** UC-064
- **Story:** As a roleplayer, I want a session export to carry only that session's own memos, so that exporting one session doesn't pull in unrelated material.
- **Acceptance criteria:**
  - **US-081.AC-1** — Given the roleplayer selects a session to export, when the export is produced, then it carries only that session's own memos — no character or setup memos are included.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2, challenge C12.

### US-082 — An imported session arrives without character or setup context
- **Actor:** ACT-002 · **Feature:** FEAT-018 · **Exercises:** UC-064
- **Story:** As a roleplayer, I want to know that an imported single-session export won't carry the character persona or setup, so that I understand what I'm getting before I rely on it.
- **Acceptance criteria:**
  - **US-082.AC-1** — Given a single-session export is imported, when the import completes, then the imported session carries no character persona.
  - **US-082.AC-2** — Given a single-session export is imported, when the import completes, then the imported session carries no setup.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2, challenge C12.

### US-136 — Import merges as new items and never reuses an id
- **Actor:** ACT-002 · **Feature:** FEAT-018 · **Exercises:** UC-062, UC-063, UC-064
- **Story:** As a roleplayer, I want an import to arrive as new material rather than overwrite what's already there, so that importing is never a way to accidentally destroy existing data.
- **Acceptance criteria:**
  - **US-136.AC-1** — Given an instance that already holds data, when material is imported, then it arrives alongside what is there and nothing existing is overwritten or replaced.
  - **US-136.AC-2** — Given imported material carries ids that already exist in the instance, when it is imported, then it arrives under fresh identity so no existing row is reused or replaced.
- **Source:** `[confirmed: user]` interview 2026-09-28, gap-closure round, challenge C29.
<!-- product-spec:end -->
