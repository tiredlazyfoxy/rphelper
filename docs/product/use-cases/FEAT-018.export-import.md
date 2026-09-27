<!-- product-spec:start -->
# FEAT-018 — Export & import — use cases

### UC-061 — Export and import the whole database, opaque to the administrator
- **Actor:** ACT-001
- **Feature:** FEAT-018
- **Preconditions:** Administrator is authenticated.
- **Main flow:**
  1. Administrator requests a whole-database export.
  2. Instance produces the export file.
  3. Administrator imports the export, into another instance or the same one (UC-002).
  4. Instance restores every user's data as it was.
- **Postconditions:** The export gives the administrator no viewer, no search and no rendering of any user's content — opaque to them at every step (FEAT-019).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2, challenge C1.

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
- **Postconditions:** The imported session arrives without the character persona and setup that gave it meaning — accepted consequence (challenge C12).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2, challenge C12.
<!-- product-spec:end -->
