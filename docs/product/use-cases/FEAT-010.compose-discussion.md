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
  - The LLM is unreachable mid-discussion — nothing the roleplayer typed is lost, the entry and discussion survive intact, the failure is visible, and a fresh candidate can be produced; the same control asks for a different candidate on any exchange, failed or not.
- **Postconditions:** Discussion attached to the answer entry; nothing lost on failure.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 4, round 9; finalization 2026-10-06, C45.

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
  3. Candidate appears in the current zone, available to promote or edit (UC-035).
- **Postconditions:** Candidate sits in the current zone; nothing is settled yet.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7, round 8.

### UC-035 — Promote, write or edit in the current zone and settle
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-010
- **Preconditions:** The current zone is open below the ruler for the entry being worked on.
- **Main flow:**
  1. Roleplayer either promotes an assistant candidate, writes their own text from scratch, or edits a candidate, in the current zone.
  2. Roleplayer settles the answer.
  3. Instance takes whatever the current zone holds at that moment as the settled answer.
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

### UC-079 — Follow a live discussion inline beneath the answer it belongs to
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-010
- **Preconditions:** A discussion is open (UC-032).
- **Main flow:**
  1. Roleplayer views the stream — the session's settled record and the live discussion together.
  2. Discussion appears inline, beneath the answer being worked on.
  3. Assistant's tool calls and thinking appear expanded while it works.
  4. Instance tucks the tool calls and thinking away once the assistant finishes.
  5. Roleplayer re-expands them at any time.
- **Postconditions:** Settling the answer collapses the discussion in place, in the same stream (UC-036).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 11, round 14.

### UC-083 — Work in the current zone below the ruler
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-010
- **Preconditions:** Session is open.
- **Main flow:**
  1. Roleplayer views the ruler separating the settled record above from exactly one current zone below.
  2. Roleplayer or assistant adds messages to the current zone.
  3. Roleplayer edits any message in the current zone, the assistant's included, before settling.
  4. Roleplayer presses Settle.
  5. Instance takes the last message in the current zone, whoever wrote it, files it as the entry, moves the ruler below it, and opens an empty current zone.
- **Alternate flows:**
  - The current zone's kind switch is set to partner — pasting text files a partner entry immediately with no Settle press (US-121).
  - The last message settled is wholly wrapped in double parentheses — the entry files as a decision, not a turn (UC-081).
  - The current zone is empty — the roleplayer abandons it; the instance discards it and the entry returns to how it was (UC-086).
  - The current zone holds text — abandoning is not offered; the roleplayer settles instead, and settling never requires an assistant answer (UC-086).
- **Postconditions:** A settled block is re-openable only while the current zone below it is still empty (US-128).
- **Source:** `[confirmed: user]` interview 2026-09-28, round 17, gap-closure round.

### UC-085 — Stop model work in flight
- **Actor:** ACT-002
- **Feature:** FEAT-010
- **Preconditions:** Model work is in flight — a discussion generation, a tool call being waited on, or a partner-text translation.
- **Main flow:**
  1. Roleplayer stops the work in flight.
  2. Instance ends the work.
  3. Instance keeps whatever text was produced so far as a usable candidate.
- **Alternate flows:**
  - A tool call is stopped — the exchange ends and whatever text was produced is kept. Deliberately unlike a *failed* tool, which the assistant is told about and carries on without (UC-051, UC-053): a failed tool leaves the exchange alive, a stop does not.
  - A translation is stopped — the original text stands and the translation is not cached. Best-effort rather than guaranteed, unlike a *failed* translation, which caches nothing at all (UC-039).
- **Postconditions:** Nothing is waiting on the model; partial output is kept and usable.
- **Source:** `[confirmed: user]` interview 2026-09-28, gap-closure round; finalization 2026-10-06, C38.

### UC-086 — Abandon a current zone without settling
- **Actor:** ACT-002
- **Feature:** FEAT-010
- **Preconditions:** A current zone is open.
- **Main flow:**
  1. The current zone is empty.
  2. Roleplayer abandons it.
  3. Instance discards it and the entry returns to how it was.
- **Alternate flows:**
  - The zone holds text — abandoning is not available; the roleplayer settles instead, and settling never requires an assistant answer.
- **Postconditions:** Nothing the roleplayer wrote is ever discarded by abandoning.
- **Source:** `[confirmed: user]` interview 2026-09-28, gap-closure round.

### UC-084 — Give the assistant a fast instruction inside a draft
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-010
- **Preconditions:** Roleplayer is drafting a message in the current zone.
- **Main flow:**
  1. Roleplayer writes a fast instruction wrapped in double parentheses inside an otherwise ordinary draft.
  2. Roleplayer settles the draft as a turn.
  3. Instance files the prose only — the parenthesised instruction never appears in the settled turn, and the assistant does not reproduce it in the prose.
- **Alternate flows:**
  - The roleplayer writes a message wholly wrapped in double parentheses — it is out-of-character; settling it files a decision, not a turn (UC-081). OOC messages are in the preferred language, and the assistant answers OOC in kind; candidates stay in the RP language regardless.
- **Postconditions:** A fast instruction shapes the assistant's next candidate but never becomes part of the record.
- **Source:** `[confirmed: user]` interview 2026-09-28, round 17.
<!-- product-spec:end -->
