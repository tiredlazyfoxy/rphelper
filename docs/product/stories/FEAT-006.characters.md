<!-- product-spec:start -->
# FEAT-006 — Characters — stories

### US-020 — Create a character
- **Actor:** ACT-002 · **Feature:** FEAT-006 · **Exercises:** UC-017
- **Story:** As a roleplayer, I want to create a character, so that I have a persona to compose replies as.
- **Acceptance criteria:**
  - **US-020.AC-1** — Given the roleplayer is authenticated, when they supply persona details and save, then the instance creates the character.
  - **US-020.AC-2** — Given the character was created, when the roleplayer opens their character list, then the new character appears in it.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 3.

### US-021 — Edit the persona
- **Actor:** ACT-002 · **Feature:** FEAT-006 · **Exercises:** UC-018
- **Story:** As a roleplayer, I want to edit a character's persona, so that it stays accurate as the character develops.
- **Acceptance criteria:**
  - **US-021.AC-1** — Given a character exists, when the roleplayer edits its persona details and saves, then the instance saves the changes.
  - **US-021.AC-2** — Given the persona was edited, when a later session under that character runs, then it uses the updated persona.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 3.

### US-022 — The character list is mine alone
- **Actor:** ACT-002 · **Feature:** FEAT-006 · **Exercises:** UC-019
- **Story:** As a roleplayer, I want my character list to show only my own characters, so that another user's characters never appear alongside mine.
- **Acceptance criteria:**
  - **US-022.AC-1** — Given the roleplayer opens the character list, when it is shown, then only the roleplayer's own characters appear.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 3.

### US-086 — Archive a character and restore it
- **Actor:** ACT-002 · **Feature:** FEAT-006 · **Exercises:** UC-067
- **Story:** As a roleplayer, I want to archive a character and restore it later, so that I can tidy my working list without losing anything.
- **Acceptance criteria:**
  - **US-086.AC-1** — Given a character exists, when the roleplayer archives it, then it leaves the working character list.
  - **US-086.AC-2** — Given a character is archived, when the roleplayer restores it, then it reappears in the working list.
  - **US-086.AC-3** — Given a character is archived, when any time passes, then the character is not destroyed — it remains recoverable.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 10.
<!-- product-spec:end -->
