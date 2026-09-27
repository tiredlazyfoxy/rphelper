<!-- product-spec:start -->
# FEAT-007 — Setups — stories

### US-023 — Create a setup under a character
- **Actor:** ACT-002 · **Feature:** FEAT-007 · **Exercises:** UC-020
- **Story:** As a roleplayer, I want to create a setup under a character, so that I have a reusable situation with its own memos and a search anchor.
- **Acceptance criteria:**
  - **US-023.AC-1** — Given a character exists, when the roleplayer creates a setup under it, then the instance saves the setup.
  - **US-023.AC-2** — Given the setup was saved, when the roleplayer starts a new session under that character, then the setup is available to choose.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 3.

### US-024 — A session with no setup works end to end
- **Actor:** ACT-002 · **Feature:** FEAT-007 · **Exercises:** UC-021
- **Story:** As a roleplayer, I want to run a session with no setup at all, so that I'm never forced to invent a setup just to start roleplaying.
- **Acceptance criteria:**
  - **US-024.AC-1** — Given a character exists with no setup created under it, when the roleplayer starts a new session and chooses none, then the instance starts the session.
  - **US-024.AC-2** — Given a session has no setup, when the roleplayer adds entries and composes discussions in it, then every capability works exactly as it would with a setup present.
  - **US-024.AC-3** — Given no setup exists anywhere under the character, when the roleplayer starts a session, then no flow requires them to choose or create a setup first.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 3, round 6.

### US-025 — Two sessions share one setup
- **Actor:** ACT-002 · **Feature:** FEAT-007 · **Exercises:** UC-022
- **Story:** As a roleplayer, I want to reuse one setup across several sessions, so that I don't recreate the same situation for every session.
- **Acceptance criteria:**
  - **US-025.AC-1** — Given a setup exists under a character, when the roleplayer starts a new session under that character and chooses the existing setup, then the instance attaches the setup to the new session.
  - **US-025.AC-2** — Given two sessions share the same setup, when either session's memo chain or search anchor resolves, then it does so independently of the other session.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 3.

### US-087 — Archive a setup and restore it
- **Actor:** ACT-002 · **Feature:** FEAT-007 · **Exercises:** UC-068
- **Story:** As a roleplayer, I want to archive a setup and restore it later, so that I can tidy my working list without losing anything.
- **Acceptance criteria:**
  - **US-087.AC-1** — Given a setup exists, when the roleplayer archives it, then it leaves the working setup list.
  - **US-087.AC-2** — Given a setup is archived, when the roleplayer restores it, then it reappears in the working list.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 10.
<!-- product-spec:end -->
