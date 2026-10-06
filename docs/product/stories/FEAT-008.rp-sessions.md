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

### US-117 — Writing the first message on a character's page creates the session
- **Actor:** ACT-002 · **Feature:** FEAT-008 · **Exercises:** UC-080
- **Story:** As a roleplayer, I want to just start typing on a character's page, so that beginning a new roleplay doesn't need a separate "create session" step first.
- **Acceptance criteria:**
  - **US-117.AC-1** — Given a character's page with no session yet started from it, when the roleplayer writes a message in its composer, then the instance creates a new session under that character with a turn being drafted.
  - **US-117.AC-2** — Given the session was just created this way, when the roleplayer views the drafted turn, then the written message is the opening message of that turn's discussion.
  - **US-117.AC-3** — Given the roleplayer writes the first message on a character's page, when the session is created, then the assistant answers that message as it would any other discussion message.
  - **US-117.AC-4** — Given the character page's composer, when the roleplayer looks at it before writing, then it offers neither the kind switch nor a setup choice.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 15; 2026-09-28, gap-closure round.

### US-145 — A session is identified by its start time, not a title
- **Actor:** ACT-002 · **Feature:** FEAT-008 · **Exercises:** UC-026, UC-059
- **Story:** As a roleplayer, I want sessions identified without naming them, so that starting a roleplay needs no naming step.
- **Acceptance criteria:**
  - **US-145.AC-1** — Given a session exists, when the roleplayer looks for a way to name or title it, then none is offered.
  - **US-145.AC-2** — Given a session appears in a listing or a search result, when the roleplayer reads it, then it is labelled by its start time.
- **Source:** `[confirmed: user]` finalization 2026-10-06, challenge C51 (plan 011 forward note).
<!-- product-spec:end -->
