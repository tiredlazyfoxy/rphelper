<!-- product-spec:start -->
# FEAT-008 — RP sessions — stories

### US-026 — Start a session
- **Actor:** ACT-002 · **Feature:** FEAT-008 · **Exercises:** UC-023
- **Story:** As a roleplayer, I want to start a session under a character, so that I have a place to run that roleplay.
- **Acceptance criteria:**
  - **US-026.AC-1** — Given a character exists, when the roleplayer starts a new session under it, then the instance creates the session, empty of entries.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 3, round 7.

### US-027 — Archive then restore and resume
- **Actor:** ACT-002 · **Feature:** FEAT-008 · **Exercises:** UC-025
- **Story:** As a roleplayer, I want to archive a session and restore it later, so that I can tidy my working list without losing the roleplay.
- **Acceptance criteria:**
  - **US-027.AC-1** — Given a session exists, when the roleplayer archives it, then it leaves the working session list.
  - **US-027.AC-2** — Given a session is archived, when the roleplayer restores it, then it reappears in the working list.
  - **US-027.AC-3** — Given a restored session, when the roleplayer resumes it, then it reopens with every entry and settled answer intact.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 3, round 7, round 10.

### US-028 — List ordered by last use
- **Actor:** ACT-002 · **Feature:** FEAT-008 · **Exercises:** UC-026
- **Story:** As a roleplayer, I want my sessions ordered by last use, so that the one I was just working on is easy to find.
- **Acceptance criteria:**
  - **US-028.AC-1** — Given the roleplayer has more than one session, when they open the session list, then sessions are ordered by last use, most recent first.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### US-029 — Sessions are mine alone
- **Actor:** ACT-002 · **Feature:** FEAT-008 · **Exercises:** UC-024
- **Story:** As a roleplayer, I want to see and resume only my own sessions, so that another user's sessions never appear in my list.
- **Acceptance criteria:**
  - **US-029.AC-1** — Given the roleplayer opens the session list, when it is shown, then only the roleplayer's own sessions appear.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 3, round 7.
<!-- product-spec:end -->
