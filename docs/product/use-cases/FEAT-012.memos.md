<!-- product-spec:start -->
# FEAT-012 — Memos — use cases

### UC-042 — Create a memo at any of the four levels
- **Actor:** ACT-002
- **Feature:** FEAT-012
- **Preconditions:** Roleplayer is authenticated; the target level (user, character, setup, session) exists.
- **Main flow:**
  1. Roleplayer chooses a level — user, character, setup, or session.
  2. Roleplayer writes the memo's content.
  3. Instance saves it at the chosen level, enabled and not forced, the default on creation.
- **Postconditions:** Memo exists, feeding the memo chain of every session it scopes (UC-046).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5, round 6, round 12.

### UC-043 — Edit a memo in markdown with live preview
- **Actor:** ACT-002
- **Feature:** FEAT-012
- **Preconditions:** Memo exists.
- **Main flow:**
  1. Roleplayer opens a memo for editing.
  2. Roleplayer writes markdown content — headings, lists, emphasis, links.
  3. Instance renders a live preview as the roleplayer writes.
  4. Roleplayer saves the memo.
- **Postconditions:** Memo content updated; preview always matched the saved markdown.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5.

### UC-044 — Set a memo's state
- **Actor:** ACT-002
- **Feature:** FEAT-012
- **Preconditions:** Memo exists.
- **Main flow:**
  1. Roleplayer opens a memo.
  2. Roleplayer sets its forced flag (forced / not forced) and its enabled flag (enabled / disabled) independently.
  3. Instance saves both flags.
- **Alternate flows:**
  - Roleplayer re-enables a disabled memo — the memo returns to whatever forced state it had when it was disabled; the roleplayer does not choose again.
- **Postconditions:** A memo always carries both flags; disabled always wins regardless of the forced flag (UC-045).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 11, round 12.

### UC-045 — Forced memos reach the system prompt
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-012
- **Preconditions:** A memo is enabled and forced (UC-044).
- **Main flow:**
  1. Roleplayer opens a session within the memo's scope.
  2. Instance includes every enabled, forced memo's content in what the assistant is given for every message in that session, in the roleplayer's arranged order within a fixed level order (user, character, setup, session).
- **Postconditions:** An enabled, forced memo is always present to the assistant in scope; it never requires a tool call. A disabled memo is excluded regardless of its forced flag.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 11, round 12.

### UC-046 — Resolve a session's memo chain, with or without a setup
- **Actor:** ACT-002
- **Feature:** FEAT-012
- **Preconditions:** Session is open, with or without a setup.
- **Main flow:**
  1. Roleplayer opens a session.
  2. Instance resolves the memo chain: session's own memos, plus the setup's when one is chosen, plus the character's, plus the user's.
  3. Chain feeds enabled+forced memos into context and enabled, not-forced memos into `memo_search` (FEAT-014).
- **Postconditions:** With no setup, the chain degrades to user + character + session with no gap.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 6, round 12.

### UC-075 — Change a note's forced and enabled state from the wall
- **Actor:** ACT-002
- **Feature:** FEAT-012
- **Preconditions:** Note exists, wall is open (FEAT-020).
- **Main flow:**
  1. Roleplayer changes a note's forced flag (forced / not forced) from the wall, without leaving it.
  2. Roleplayer changes a note's enabled flag (enabled / disabled) from the wall, without leaving it.
  3. Instance saves the changed flag immediately.
- **Alternate flows:**
  - Roleplayer disables a forced note — the forced flag is kept and restored automatically on re-enable (UC-044).
- **Postconditions:** The two flags always change independently of each other.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 11, round 12.

### UC-076 — Reorder notes within a level
- **Actor:** ACT-002
- **Feature:** FEAT-012
- **Preconditions:** A level (user, character, setup or session) holds more than one note.
- **Main flow:**
  1. Roleplayer drags a note within its own level's group on the wall.
  2. Instance saves the new order for that level.
- **Alternate flows:**
  - Roleplayer attempts to drag a note into a different level's group — the instance does not allow it; levels keep a fixed order (user, character, setup, session) and a note cannot move between them by dragging.
- **Postconditions:** Forced notes in that level enter the system prompt in the new order (UC-045); order has no observable effect on disabled or not-forced notes.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 11, round 12.

### UC-088 — Remove a note by emptying it
- **Actor:** ACT-002
- **Feature:** FEAT-012
- **Preconditions:** A note exists at one of the four levels (UC-042).
- **Main flow:**
  1. Roleplayer clears all of a saved note's text.
  2. Roleplayer moves focus away from the note.
  3. Instance removes the note.
- **Alternate flows:**
  - The roleplayer creates a note and leaves it without entering any text — nothing is persisted and no note appears.
- **Postconditions:** Emptying a note is the only way a note is removed. There is no separate delete action, and notes have no archived state (FEAT-012).
- **Source:** `[confirmed: user]` plan 015 decision 2026-10-02, confirmed at finalization 2026-10-06, challenge C40.
<!-- product-spec:end -->
