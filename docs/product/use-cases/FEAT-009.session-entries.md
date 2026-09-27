<!-- product-spec:start -->
# FEAT-009 — Session entries & the RP flow — use cases

### UC-027 — Add a partner entry by pasting
- **Actor:** ACT-002
- **Feature:** FEAT-009
- **Preconditions:** Session is open.
- **Main flow:**
  1. Roleplayer pastes the partner's text into the session.
  2. Instance adds it as a new partner entry, in the RP language as pasted.
  3. Entry appears in the session.
- **Exception flows:**
  - The paste is enormous — instance warns about its context cost, but adds the entry regardless; pasting is never refused.
- **Postconditions:** Partner entry present in the session, available for translation (FEAT-011) and for discussion (FEAT-010).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 4, round 9.

### UC-028 — Add my own answer entry directly
- **Actor:** ACT-002
- **Feature:** FEAT-009
- **Preconditions:** Session is open.
- **Main flow:**
  1. Roleplayer writes an answer directly, with no discussion.
  2. Roleplayer settles it.
  3. Instance adds it as a settled answer entry, in the RP language.
- **Postconditions:** Answer entry present in the session, editable at any time (UC-029).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 4, round 7.

### UC-029 — Edit any entry at any time
- **Actor:** ACT-002
- **Feature:** FEAT-009
- **Preconditions:** Entry exists, of any age.
- **Main flow:**
  1. Roleplayer opens an existing entry, however old.
  2. Roleplayer edits its text.
  3. Instance saves the edit.
- **Postconditions:** The assistant always reads the current version of every entry — editing an old answer changes what session context says happened.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 6.

### UC-030 — Copy a settled answer
- **Actor:** ACT-002
- **Feature:** FEAT-009
- **Preconditions:** A settled answer entry exists.
- **Main flow:**
  1. Roleplayer selects a settled answer.
  2. Roleplayer copies it.
  3. Instance places the answer's RP-language text on the clipboard.
- **Postconditions:** Nothing else changes — no sent-state is recorded.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### UC-031 — Add entries in any order (open the RP myself, or answer twice running)
- **Actor:** ACT-002
- **Feature:** FEAT-009
- **Preconditions:** Session is open.
- **Main flow:**
  1. Roleplayer adds entries to the session in whatever order the roleplay calls for.
- **Alternate flows:**
  - Roleplayer opens the RP themselves — the first entry is their own answer, with no partner block before it.
  - Roleplayer posts two answers running — no partner entry between them.
  - Roleplayer pastes several partner blocks in sequence — no answer between them.
- **Postconditions:** No partner-block → discussion → answer triple is enforced; entries stay independent.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 4.
<!-- product-spec:end -->
