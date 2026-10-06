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
- **Story:** As a roleplayer, I want to promote an assistant candidate into the current zone and edit it, so that the final answer is exactly as I want it.
- **Acceptance criteria:**
  - **US-038.AC-1** — Given a candidate sits in the current zone, when the roleplayer promotes it, then it becomes the current zone's contents, editable.
  - **US-038.AC-2** — Given a promoted candidate sits in the current zone, when the roleplayer edits it and settles, then the instance takes the edited text as the settled answer.
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
  - **US-040.AC-2** — Given a discussion has collapsed, when the roleplayer looks at its collapsed row, then no message count is shown on it.
  - **US-040.AC-3** — Given a collapsed discussion has been opened, when the roleplayer reads it, then its message count is shown.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 4; finalization 2026-10-06, C53.

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
  - **US-044.AC-3** — Given the LLM was unreachable mid-discussion, when the roleplayer acts on the visible failure, then the assistant produces a fresh candidate for that exchange.
  - **US-044.AC-4** — Given a generation failed for any reason, when the failure is shown, then it states the reason, and the reason does not persist once the notice has gone.
  - **US-044.AC-5** — Given an exchange that did not fail, when the roleplayer asks for a different candidate, then the assistant produces a fresh one for that same exchange.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 4, round 9; 2026-09-28, gap-closure round, challenge C23; finalization 2026-10-06, C45.

### US-113 — A discussion appears beneath its answer in the same stream, and collapses there when the answer is settled
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-079
- **Story:** As a roleplayer, I want the discussion in the same stream as the session's entries, not a separate pane, so that following the roleplay and composing my reply are one continuous view.
- **Acceptance criteria:**
  - **US-113.AC-1** — Given a discussion is open on an answer, when the roleplayer views the stream, then the discussion appears inline beneath that answer, alongside the session's settled entries.
  - **US-113.AC-2** — Given the roleplayer settles the answer, when the stream updates, then the discussion collapses in place, in the same stream.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 11, round 14.

### US-114 — The assistant's tool calls and thinking are visible while it works and are tucked away once it finishes
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-010 · **Exercises:** UC-079
- **Story:** As a roleplayer, I want to see what the assistant is doing while it works, so that I understand where a candidate came from.
- **Acceptance criteria:**
  - **US-114.AC-1** — Given the assistant is producing a candidate, when it calls a tool or reasons, then the tool call and its thinking are shown expanded while it works.
  - **US-114.AC-2** — Given the assistant finishes, when its tool calls and thinking have completed, then they are tucked away, out of view by default.
  - **US-114.AC-3** — Given tool calls and thinking are tucked away, when the roleplayer re-expands them, then they are still viewable, at any later time.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 14.

### US-115 — Any message in the current zone is edited in place, the assistant's included, not findable by session search, with no new reply
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-010 · **Exercises:** UC-083
- **Story:** As a roleplayer, I want to edit any message in the current zone before I settle, including one the assistant wrote, so that the final wording is always mine to control.
- **Acceptance criteria:**
  - **US-115.AC-1** — Given a message the roleplayer or the assistant wrote sits in the current zone, when the roleplayer edits its text, then the instance saves the edit in place.
  - **US-115.AC-2** — Given a message in the current zone was edited, when the edit saves, then that message's text is not findable by session search — only settled entries are.
  - **US-115.AC-3** — Given a message in the current zone was edited, when the edit saves, then the assistant does not produce a new reply on its own.
- **Constraint:** A tool's own record is not a message anyone wrote, and is not editable.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 12; 2026-09-28, round 17; finalization 2026-10-06, C46.

### US-116 — A collapsed discussion cannot be edited
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-079
- **Story:** As a roleplayer, I want a collapsed discussion locked, so that I can't accidentally alter something that's already out of context.
- **Acceptance criteria:**
  - **US-116.AC-1** — Given a discussion has collapsed, when the roleplayer opens it to read, then no message inside it is editable.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 12.

### US-125 — A ruler separates the settled record above from exactly one current zone below
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-083
- **Story:** As a roleplayer, I want a visible ruler marking where the settled record ends, so that I always know what's already recorded and what's still in progress.
- **Acceptance criteria:**
  - **US-125.AC-1** — Given a session is open, when the roleplayer views the stream, then a ruler separates the settled record above it from a single current zone below it.
- **Source:** `[confirmed: user]` interview 2026-09-28, round 17.

### US-126 — Settle takes the last message in the current zone, whoever wrote it
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-083
- **Story:** As a roleplayer, I want Settle to take whatever is last in the current zone, so that promoting the assistant's own wording doesn't need a separate copy step.
- **Acceptance criteria:**
  - **US-126.AC-1** — Given the current zone's last message was written by the assistant, when the roleplayer presses Settle, then that message becomes the settled entry's text.
  - **US-126.AC-2** — Given the current zone's last message was written by the roleplayer, when they press Settle, then that message becomes the settled entry's text.
- **Source:** `[confirmed: user]` interview 2026-09-28, round 17.

### US-127 — Settling files the entry, moves the ruler below it, and opens an empty current zone
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-083
- **Story:** As a roleplayer, I want the ruler to move and a fresh current zone to open the moment I settle, so that I can keep going without any manual cleanup.
- **Acceptance criteria:**
  - **US-127.AC-1** — Given the roleplayer presses Settle, when the entry is filed, then the ruler moves to sit below the newly settled entry.
  - **US-127.AC-2** — Given the ruler has moved, when the roleplayer views the stream, then the current zone below it is empty.
- **Source:** `[confirmed: user]` interview 2026-09-28, round 17.

### US-128 — A settled block is re-openable only while the current zone below it is still empty
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-083
- **Story:** As a roleplayer, I want to undo a mis-settled entry while nothing has followed it yet, so that a slip doesn't lock in the wrong text.
- **Acceptance criteria:**
  - **US-128.AC-1** — Given a settled entry's current zone is still empty, when the roleplayer re-opens it, then it re-opens as an active discussion.
  - **US-128.AC-2** — Given a settled entry's current zone already holds a message, when the roleplayer tries to re-open it, then re-opening is refused.
- **Source:** `[confirmed: user]` interview 2026-09-28, round 17.

### US-129 — A wholly-parenthesised message is out-of-character; settling one files a decision, not a turn
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-084, UC-081
- **Story:** As a roleplayer, I want a message that's entirely OOC to settle as a decision, so that stepping out of character never gets mistaken for the character's own turn.
- **Acceptance criteria:**
  - **US-129.AC-1** — Given the current zone's last message is wholly wrapped in double parentheses, when the roleplayer settles it, then the instance files it as a decision entry, not a turn.
- **Source:** `[confirmed: user]` interview 2026-09-28, round 17.

### US-130 — A double-parenthesised fragment inside a draft is an instruction that never appears in the settled turn
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-010 · **Exercises:** UC-084
- **Story:** As a roleplayer, I want to slip a fast instruction into my draft without it becoming part of the posted text, so that I can steer the reply without editing it out afterward.
- **Acceptance criteria:**
  - **US-130.AC-1** — Given a draft contains a double-parenthesised fragment alongside ordinary prose, when the roleplayer settles it as a turn, then the fragment is absent from the settled turn's text.
  - **US-130.AC-2** — Given a draft contained a double-parenthesised fragment, when the assistant produces the next candidate, then it does not reproduce the fragment's text in the prose.
- **Constraint:** The `(( ))` convention assumes double parentheses never occur in the roleplayer's RP prose itself. Examined and held, not an oversight — the roleplayer confirmed this never happens in their RP.
- **Source:** `[confirmed: user]` interview 2026-09-28, round 17, challenge C24.

### US-131 — OOC messages are in the preferred language; the assistant answers OOC in kind, while candidates stay in the RP language
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-010 · **Exercises:** UC-084
- **Story:** As a roleplayer, I want to step out of character in my own preferred language and get an answer in kind, so that talking to the assistant as myself never forces me into the RP language.
- **Acceptance criteria:**
  - **US-131.AC-1** — Withdrawn: unfalsifiable — the language the roleplayer types in is their own habit, not a product obligation.
  - **US-131.AC-2** — Given the roleplayer writes an OOC message, when the assistant replies, then the reply is in the preferred language.
  - **US-131.AC-3** — Given an OOC exchange is underway, when the assistant produces a candidate reply, then the candidate is in the RP language regardless.
- **Source:** `[confirmed: user]` interview 2026-09-28, round 17.

### US-132 — Stopping keeps the partial text as a usable candidate
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-085
- **Story:** As a roleplayer, I want to stop a generation and keep what it produced so far, so that a runaway or unwanted reply doesn't cost me the work already done.
- **Acceptance criteria:**
  - **US-132.AC-1** — Given a generation has streamed partial text, when the roleplayer stops it, then the text produced so far remains as a candidate they can use or edit.
  - **US-132.AC-2** — Given the roleplayer stopped a generation, when they look at the discussion, then nothing is waiting on the model.
- **Source:** `[confirmed: user]` interview 2026-09-28, gap-closure round.

### US-133 — The stop reaches any model work
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-085
- **Story:** As a roleplayer, I want the stop to reach a tool call or a translation, not only a discussion reply, so that any runaway model work can be cut off the same way.
- **Acceptance criteria:**
  - **US-133.AC-1** — Given the assistant is waiting on a tool call, when the roleplayer stops it, then the exchange ends and whatever text was produced is kept.
  - **US-133.AC-2** — Given a partner-text translation is in flight, when the roleplayer stops it, then the original text stands and the translation is not cached.
- **Constraint:** Not caching a stopped translation is best-effort, not a guarantee — a stop arriving as the result is being written may not reach it in time. A *failed* translation caches nothing at all, which is a guarantee (UC-039).
- **Source:** `[confirmed: user]` interview 2026-09-28, gap-closure round; finalization 2026-10-06, C38.

### US-134 — An empty zone is discarded; one holding text must be settled
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-086
- **Story:** As a roleplayer, I want to discard an empty current zone I opened by mistake, but never lose text I actually wrote, so that abandoning is safe and never a trap.
- **Acceptance criteria:**
  - **US-134.AC-1** — Given a current zone with nothing written in it, when the roleplayer abandons it, then it is discarded and the entry returns to how it was.
  - **US-134.AC-2** — Given a current zone holding text, when the roleplayer looks for a way to abandon it, then none is offered — the zone can only be settled.
- **Source:** `[confirmed: user]` interview 2026-09-28, gap-closure round.

### US-135 — Settling with no assistant answer settles the roleplayer's own text
- **Actor:** ACT-002 · **Feature:** FEAT-010 · **Exercises:** UC-086
- **Story:** As a roleplayer, I want to settle a zone that only holds my own message, so that I'm never stuck waiting on the assistant to be able to move on.
- **Acceptance criteria:**
  - **US-135.AC-1** — Given a current zone holds only the roleplayer's own message and the assistant has not answered, when the roleplayer settles, then their own text is settled as-is and nothing is lost.
- **Source:** `[confirmed: user]` interview 2026-09-28, gap-closure round.

### US-146 — The assistant's thinking never enters the settled record
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-010 · **Exercises:** UC-035
- **Story:** As a roleplayer, I want the assistant's reasoning kept out of the settled text, so that what I post is only the reply itself.
- **Acceptance criteria:**
  - **US-146.AC-1** — Given a candidate holds the assistant's thinking alongside its reply, when the roleplayer settles it, then the settled entry's text holds the reply without the thinking.
  - **US-146.AC-2** — Given a candidate holds nothing but the assistant's thinking, when the roleplayer settles it, then the settled entry's text is empty.
- **Source:** `[confirmed: user]` finalization 2026-10-06, challenge C51 (plan 021 decision D4).
<!-- product-spec:end -->
