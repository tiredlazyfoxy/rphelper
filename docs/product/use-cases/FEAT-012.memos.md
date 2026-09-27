<!-- product-spec:start -->
# FEAT-012 — Memos — use cases

### UC-042 — Create a memo at any of the four levels
- **Actor:** ACT-002
- **Feature:** FEAT-012
- **Preconditions:** Roleplayer is authenticated; the target level (user, character, setup, session) exists.
- **Main flow:**
  1. Roleplayer chooses a level — user, character, setup, or session.
  2. Roleplayer writes the memo's content.
  3. Instance saves it at the chosen level with state `searchable`, the default on creation.
- **Postconditions:** Memo exists, feeding the memo chain of every session it scopes (UC-046).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5, round 6.

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
  2. Roleplayer sets its state to forced, searchable, or disabled.
  3. Instance saves the state.
- **Alternate flows:**
  - Roleplayer re-enables a disabled memo — they choose its mode, forced or searchable, again.
- **Postconditions:** Memo is in exactly one of the three states at any time.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5.

### UC-045 — Forced memos reach the system prompt
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-012
- **Preconditions:** A memo's state is `forced` (UC-044).
- **Main flow:**
  1. Roleplayer opens a session within the memo's scope.
  2. Instance includes the forced memo's content in what the assistant is given for every message in that session.
- **Postconditions:** A forced memo is always present to the assistant in scope; it never requires a tool call.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5.

### UC-046 — Resolve a session's memo chain, with or without a setup
- **Actor:** ACT-002
- **Feature:** FEAT-012
- **Preconditions:** Session is open, with or without a setup.
- **Main flow:**
  1. Roleplayer opens a session.
  2. Instance resolves the memo chain: session's own memos, plus the setup's when one is chosen, plus the character's, plus the user's.
  3. Chain feeds forced memos into context and searchable memos into `memo_search` (FEAT-014).
- **Postconditions:** With no setup, the chain degrades to user + character + session with no gap.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 6.
<!-- product-spec:end -->
