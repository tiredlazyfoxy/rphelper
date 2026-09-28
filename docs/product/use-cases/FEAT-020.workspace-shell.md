<!-- product-spec:start -->
# FEAT-020 — Workspace shell & navigation — use cases

### UC-069 — Navigate characters and their sessions from the left column
- **Actor:** ACT-002
- **Feature:** FEAT-020
- **Preconditions:** Roleplayer is authenticated.
- **Main flow:**
  1. Roleplayer opens the left column.
  2. Instance lists the roleplayer's characters, each with its sessions.
  3. Each session row shows its setup as a label, or nothing when it has none.
  4. Sessions under a character are ordered by last use.
  5. Roleplayer selects a session to open it.
- **Postconditions:** The selected session opens in the stream; the tree stays available for the next navigation.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 12, round 13.

### UC-070 — Collapse the left column to an icon rail and restore it
- **Actor:** ACT-002
- **Feature:** FEAT-020
- **Preconditions:** Left column is open.
- **Main flow:**
  1. Roleplayer collapses the left column.
  2. Instance reduces it to an icon rail.
  3. Rail keeps search, create and the user menu reachable.
  4. Roleplayer restores the column.
  5. Instance returns it to its full, expanded form.
- **Postconditions:** Search, create and the user menu are reachable in both states.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 14, round 15.

### UC-071 — Open the user menu and reach logout, settings, or the admin area
- **Actor:** ACT-002 (+ ACT-001)
- **Feature:** FEAT-020
- **Preconditions:** Roleplayer is authenticated.
- **Main flow:**
  1. Roleplayer opens the user menu.
  2. Instance shows logout and a settings entry; an admin entry point appears only for ACT-001.
  3. Roleplayer chooses logout, settings, or (ACT-001 only) the admin area.
  4. Instance takes the roleplayer to the chosen destination.
- **Alternate flows:**
  - Roleplayer chooses settings — the settings screen carries the two languages (FEAT-013) and the roleplayer's own user-level notes (FEAT-012).
- **Postconditions:** Logout ends the session (FEAT-002); the admin entry point is never shown to ACT-002.
- **Source:** `[confirmed: user]` original feature request — user menu:
  logout, settings (languages + notes), admin link if admin.

### UC-072 — Open, pin and dismiss the note wall beside the stream
- **Actor:** ACT-002
- **Feature:** FEAT-020
- **Preconditions:** A session is open.
- **Main flow:**
  1. Roleplayer opens the note wall.
  2. Instance shows the wall over the stream.
  3. Roleplayer pins the wall.
  4. Instance keeps the wall open until the roleplayer dismisses it.
  5. Roleplayer dismisses the wall.
- **Alternate flows:**
  - No session is open — the note wall is not shown at all; user-level notes are reached through the user menu's settings instead (UC-071).
- **Postconditions:** A pinned wall's state survives a reload.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 14.

### UC-073 — Work on a character's page — persona, notes, setups, settings, sessions
- **Actor:** ACT-002
- **Feature:** FEAT-020
- **Preconditions:** Character exists.
- **Main flow:**
  1. Roleplayer opens a character's page.
  2. Instance shows the character's persona (FEAT-006), its notes (FEAT-012), its setups (FEAT-007), its configuration (FEAT-013) and its sessions (FEAT-008) in one place.
  3. Roleplayer works on any of these without navigating away.
- **Postconditions:** Every character-scoped concern is reachable from a single page.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 13.

### UC-074 — Create a character from a draft page
- **Actor:** ACT-002
- **Feature:** FEAT-020
- **Preconditions:** Roleplayer is authenticated.
- **Main flow:**
  1. Roleplayer opens character creation.
  2. Instance opens a draft page with nothing yet persisted.
  3. Roleplayer enters something real (e.g. a name or persona detail).
  4. Instance persists the character on that first real input.
- **Alternate flows:**
  - Roleplayer leaves the draft page without entering anything — nothing was persisted; no character exists.
- **Postconditions:** A character exists only once the roleplayer entered something real; UC-017 carries the creation flow itself.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 14.
<!-- product-spec:end -->
