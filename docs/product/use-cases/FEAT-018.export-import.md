<!-- product-spec:start -->
# FEAT-018 — Export & import — use cases

### UC-061 — Export and import the whole database, opaque to the administrator
- **Actor:** ACT-001
- **Feature:** FEAT-018
- **Preconditions:** Administrator is authenticated.
- **Main flow:**
  1. Administrator requests a whole-database export.
  2. Instance produces the export file.
  3. Administrator imports the export into an instance holding no content, either another instance or the same one brought up fresh (UC-002).
  4. Instance replaces its contents with the export's, keeping the export's own ids, so every user's data is restored exactly as it was and those users can sign in again.
- **Exception flows:**
  - The target database already holds content — the import is refused and nothing is replaced (US-077.AC-3).
- **Postconditions:** The export gives the administrator no viewer, no search and no rendering of any user's content — opaque to them at every step (FEAT-019). A whole-database import is a restore, not a merge: unlike the roleplayer's three granularities (US-136), it replaces rather than adds and does not mint fresh ids.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2, challenge C1; finalization 2026-10-06, C39.

### UC-062 — Export and import my own user data with memos
- **Actor:** ACT-002
- **Feature:** FEAT-018
- **Preconditions:** Roleplayer is authenticated.
- **Main flow:**
  1. Roleplayer requests an export of their own data.
  2. Instance produces the export, including the roleplayer's memos.
  3. Roleplayer imports it.
  4. Instance restores the roleplayer's characters, setups, sessions and memos.
- **Postconditions:** Imported data matches what was exported, memos included.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2.

### UC-063 — Export and import a character with its memos
- **Actor:** ACT-002
- **Feature:** FEAT-018
- **Preconditions:** Character exists.
- **Main flow:**
  1. Roleplayer selects a character to export.
  2. Instance produces the export, including the character's own memos.
  3. Roleplayer imports it.
  4. Instance restores the character and its memos.
- **Postconditions:** Imported character carries its own memos; nothing beyond the character's scope is included.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2.

### UC-064 — Export and import a single session with its own memos
- **Actor:** ACT-002
- **Feature:** FEAT-018
- **Preconditions:** Session exists.
- **Main flow:**
  1. Roleplayer selects a session to export.
  2. Instance produces the export, carrying only that session's own memos.
  3. Roleplayer imports it.
  4. Instance restores the session and its own memos.
- **Postconditions:** None of the source's character persona or setup travels with the export. The imported session arrives under a character the roleplayer chooses and takes that character's persona, with no setup — accepted consequence (challenge C12, narrowed at finalization 2026-10-06).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2, challenge C12; finalization 2026-10-06, C41.
<!-- product-spec:end -->
