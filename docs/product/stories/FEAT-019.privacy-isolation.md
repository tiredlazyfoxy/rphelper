<!-- product-spec:start -->
# FEAT-019 — Privacy & isolation — stories

### US-083 — No screen shows another user's characters, sessions or memos
- **Actor:** ACT-002 · **Feature:** FEAT-019 · **Exercises:** UC-065
- **Story:** As a roleplayer, I want every screen to show only my own characters, sessions and memos, so that my private material is never mixed with anyone else's.
- **Acceptance criteria:**
  - **US-083.AC-1** — Given the roleplayer uses any screen, when characters, sessions or memos are listed, then none belonging to another user ever appears.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 1, round 2.

### US-084 — User management shows accounts, never content
- **Actor:** ACT-001 · **Feature:** FEAT-019 · **Exercises:** UC-066
- **Story:** As an administrator, I want every administrative surface to show accounts only, never content, so that managing the instance never exposes what users wrote.
- **Acceptance criteria:**
  - **US-084.AC-1** — Given the administrator uses an administrative surface, when it is shown, then it shows administrative data only — no character, session, setup or memo content.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 1, round 2.

### US-085 — Search and tools never cross the user boundary
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-019 · **Exercises:** UC-065
- **Story:** As a roleplayer, I want my search and the assistant's tools to never reach past my own material, so that the user boundary holds everywhere, not just in listings.
- **Acceptance criteria:**
  - **US-085.AC-1** — Given the roleplayer runs `my search` or the assistant calls a tool inside their session, when results are returned, then no result belonging to another user is ever included.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 1, round 2.
<!-- product-spec:end -->
