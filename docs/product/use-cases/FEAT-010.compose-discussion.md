<!-- product-spec:start -->
# FEAT-010 — Compose discussion — use cases

### UC-032 — Open a discussion on an answer
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-010
- **Preconditions:** An answer entry is being worked on.
- **Main flow:**
  1. Roleplayer opens a discussion on an answer entry.
  2. Roleplayer and assistant exchange messages in the discussion.
  3. Discussion stays open until the roleplayer settles the answer.
- **Exception flows:**
  - The LLM is unreachable mid-discussion — nothing the roleplayer typed is lost, the entry and discussion survive intact, the failure is visible, retry is possible.
- **Postconditions:** Discussion attached to the answer entry; nothing lost on failure.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 4, round 9.

### UC-033 — Discuss in any language, the assistant mirrors each message
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-010
- **Preconditions:** Discussion is open (UC-032).
- **Main flow:**
  1. Roleplayer writes a discussion message in whichever language they choose — preferred language, RP language, or a mix.
  2. Assistant replies in the language of that message.
  3. Roleplayer may switch language message to message; the assistant keeps mirroring.
- **Postconditions:** No fixed discussion language exists; candidate replies are nonetheless always produced in the RP language (UC-034).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 8.

### UC-034 — The assistant produces a candidate reply in the RP language
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-010
- **Preconditions:** Discussion is open.
- **Main flow:**
  1. Roleplayer asks the assistant for a candidate reply.
  2. Assistant produces a candidate in the RP language.
  3. Candidate appears in the answer box, available to promote or edit (UC-035).
- **Postconditions:** Candidate sits in the answer box; nothing is settled yet.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7, round 8.

### UC-035 — Promote, write or edit into the answer box and settle
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-010
- **Preconditions:** An answer box exists for the entry being worked on.
- **Main flow:**
  1. Roleplayer either promotes an assistant candidate, writes their own text from scratch, or edits a candidate, in the answer box.
  2. Roleplayer settles the answer.
  3. Instance takes whatever the answer box holds at that moment as the settled answer.
- **Postconditions:** The assistant never writes into the session directly — only the roleplayer's settling action commits the answer.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### UC-036 — The discussion collapses on settling and stays readable
- **Actor:** ACT-002
- **Feature:** FEAT-010
- **Preconditions:** Discussion open on an answer (UC-032).
- **Main flow:**
  1. Roleplayer settles the answer (UC-035).
  2. Discussion collapses out of view as an active exchange.
  3. Roleplayer can still open the collapsed discussion and read every message in it.
- **Postconditions:** Collapsed discussion stays readable; only the settled answer, not the discussion, feeds session context going forward.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 4.

### UC-037 — Re-open a collapsed discussion while nothing follows it
- **Actor:** ACT-002
- **Feature:** FEAT-010
- **Preconditions:** Discussion collapsed (UC-036); no entry has been added after the answer it belongs to.
- **Main flow:**
  1. Roleplayer opens the collapsed discussion.
  2. Instance re-opens it as an active discussion, editable again.
- **Exception flows:**
  - An entry already follows the answer — re-open is refused; the discussion stays collapsed and readable only.
- **Postconditions:** Re-open succeeds only as an undo for the immediately preceding answer, not once the RP has continued.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 4.

### UC-038 — A settled discussion never reaches context again
- **Actor:** ACT-002
- **Feature:** FEAT-010
- **Preconditions:** Discussion collapsed (UC-036), whether or not still re-openable.
- **Main flow:**
  1. Roleplayer continues the session with further entries.
  2. Assistant composes further candidates from session entries and forced memos.
  3. The collapsed discussion's messages are absent from what the assistant reads.
- **Postconditions:** Only the settled answer text (RP language) ever entered context; the discussion that produced it never does, then or later — deliberate asymmetry against UC-029 (a settled answer is editable forever).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 6.
<!-- product-spec:end -->
