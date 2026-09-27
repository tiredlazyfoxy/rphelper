<!-- product-spec:start -->
# FEAT-008 — RP sessions — use cases

### UC-023 — Start a session under a character
- **Actor:** ACT-002
- **Feature:** FEAT-008
- **Preconditions:** Character exists.
- **Main flow:**
  1. Roleplayer opens a character.
  2. Roleplayer starts a new session, with or without a setup (UC-021).
  3. Instance creates the session and opens it, empty of entries.
- **Postconditions:** Session exists, ordered into the roleplayer's session list by last use (UC-026).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 3, round 7.

### UC-024 — Resume a session
- **Actor:** ACT-002
- **Feature:** FEAT-008
- **Preconditions:** Session exists and is in the working (non-archived) list.
- **Main flow:**
  1. Roleplayer opens the session list.
  2. Roleplayer selects a session.
  3. Instance opens the session where it was left, all entries and settled answers intact.
- **Alternate flows:**
  - Session is archived — roleplayer restores it (UC-025) first, then resumes.
- **Postconditions:** Session reopened with nothing lost.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 3, round 7.

### UC-025 — Archive and restore a session
- **Actor:** ACT-002
- **Feature:** FEAT-008
- **Preconditions:** Session exists.
- **Main flow:**
  1. Roleplayer archives a session.
  2. Session leaves the working session list.
  3. Roleplayer restores it.
  4. Session reappears in the working list, resumable (UC-024).
- **Postconditions:** There is no "finished" state — archiving is the only lifecycle change, and it is reversible; nothing is destroyed.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 3, round 10.

### UC-026 — See sessions ordered by last use
- **Actor:** ACT-002
- **Feature:** FEAT-008
- **Preconditions:** Roleplayer has at least one session.
- **Main flow:**
  1. Roleplayer opens the session list.
  2. Instance orders sessions by last use, most recent first.
- **Postconditions:** Every session stays resumable regardless of its position in the list — no "finished" state.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.
<!-- product-spec:end -->
