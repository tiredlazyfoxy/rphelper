<!-- product-spec:start -->
# FEAT-010 — Compose discussion — stories

### US-036 — The assistant mirrors the language of each message
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-010 · **Exercises:** UC-033
- **Story:** As a roleplayer, I want the assistant to reply in whichever language I just used, so that I can discuss freely in my preferred language, the RP language, or a mix.
- **Acceptance criteria:**
  - **US-036.AC-1** — Given a discussion is open, when the roleplayer writes a message in their preferred language, then the assistant replies in that language.
  - **US-036.AC-2** — Given a discussion is open, when the roleplayer writes a message in the RP language, then the assistant replies in the RP language.
  - **US-036.AC-3** — Given a discussion is open, when the roleplayer switches language from one message to the next, then the assistant's reply mirrors the language of the new message.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 8.

### US-037 — Candidates are produced in the RP language
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-010 · **Exercises:** UC-034
- **Story:** As a roleplayer, I want candidate replies always in the RP language, so that I can promote one straight into the roleplay regardless of what language I discussed in.
- **Acceptance criteria:**
  - **US-037.AC-1** — Given a discussion is open in any language, when the roleplayer asks the assistant for a candidate reply, then the candidate is produced in the RP language.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7, round 8.

### US-038 — Promote a candidate and edit it before settling
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-035
- **Story:** As a roleplayer, I want to promote an assistant candidate into the answer box and edit it, so that the final answer is exactly as I want it.
- **Acceptance criteria:**
  - **US-038.AC-1** — Given a candidate sits in the answer box, when the roleplayer promotes it, then it becomes the box's contents, editable.
  - **US-038.AC-2** — Given the roleplayer edits the promoted candidate and settles, then the instance takes the edited text as the settled answer.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### US-039 — Settling collapses the discussion
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-036
- **Story:** As a roleplayer, I want the discussion to collapse once I settle an answer, so that it stops taking up active space once its job is done.
- **Acceptance criteria:**
  - **US-039.AC-1** — Given a discussion is open on an answer, when the roleplayer settles the answer, then the discussion collapses out of view as an active exchange.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 4.

### US-040 — A collapsed discussion is readable
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-036
- **Story:** As a roleplayer, I want to still read a collapsed discussion, so that I can review how an answer came about.
- **Acceptance criteria:**
  - **US-040.AC-1** — Given a discussion has collapsed, when the roleplayer opens the collapsed discussion, then every message in it is still readable.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 4.

### US-041 — Re-open succeeds while it is last
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-037
- **Story:** As a roleplayer, I want to re-open the last collapsed discussion, so that I can undo a mis-click settle before the RP moves on.
- **Acceptance criteria:**
  - **US-041.AC-1** — Given a discussion is collapsed and no entry has been added after its answer, when the roleplayer opens the collapsed discussion, then it re-opens as an active discussion, editable again.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 4.

### US-042 — Re-open is refused once another entry exists
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-037
- **Story:** As a roleplayer, I want re-opening refused once the RP has continued, so that the discussion undo can't rewrite roleplay that already moved on.
- **Acceptance criteria:**
  - **US-042.AC-1** — Given a discussion is collapsed and an entry has since been added after its answer, when the roleplayer tries to open the collapsed discussion, then re-opening is refused and the discussion stays collapsed and readable only.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 4.

### US-043 — Only the settled answer enters session context
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-010 · **Exercises:** UC-038
- **Story:** As a roleplayer, I want only the settled answer to feed session context, never the discussion, so that my back-and-forth with the assistant doesn't cost context forever.
- **Acceptance criteria:**
  - **US-043.AC-1** — Given a discussion collapsed on a settled answer, when the roleplayer continues the session with further entries, then the assistant composes from the settled answer text, not the discussion.
  - **US-043.AC-2** — Given a discussion has collapsed, when any later turn is composed, then the discussion's messages do not reach the assistant on that turn or any later one.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 6.

### US-044 — The LLM going away mid-discussion loses none of my text
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-010 · **Exercises:** UC-032
- **Story:** As a roleplayer, I want nothing I typed to be lost if the LLM becomes unreachable mid-discussion, so that a connection failure never costs me my work.
- **Acceptance criteria:**
  - **US-044.AC-1** — Given a discussion is open and the roleplayer has typed text, when the LLM becomes unreachable mid-discussion, then the entry and discussion survive intact with nothing the roleplayer typed lost.
  - **US-044.AC-2** — Given the LLM was unreachable mid-discussion, when the failure occurs, then it is shown to the roleplayer visibly.
  - **US-044.AC-3** — Given the LLM was unreachable mid-discussion, when the roleplayer acts on the visible failure, then a retry is possible.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 4, round 9.
<!-- product-spec:end -->
