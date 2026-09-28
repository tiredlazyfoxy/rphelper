<!-- product-spec:start -->
# FEAT-009 — Session entries & the RP flow — stories

### US-030 — Paste a partner block
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-027
- **Story:** As a roleplayer, I want to paste the partner's text into a session, so that it becomes part of the roleplay I'm working from.
- **Acceptance criteria:**
  - **US-030.AC-1** — Given a session is open, when the roleplayer pastes the partner's text, then the instance adds it as a new partner entry, in the RP language as pasted.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 4, round 9.

### US-031 — Post an answer with no discussion
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-028
- **Story:** As a roleplayer, I want to write and settle an answer directly, with no discussion, so that I can post quickly when I don't need help.
- **Acceptance criteria:**
  - **US-031.AC-1** — Given a session is open, when the roleplayer writes an answer directly with no discussion and settles it, then the instance adds it as a settled answer entry.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 4, round 7.

### US-032 — Edit a settled answer from weeks ago
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-029
- **Story:** As a roleplayer, I want to edit a settled answer no matter how old it is, so that I can fix a typo or change what happened without restriction.
- **Acceptance criteria:**
  - **US-032.AC-1** — Given a settled answer entry exists from weeks ago, when the roleplayer edits its text, then the instance saves the edit.
  - **US-032.AC-2** — Given the entry was edited, when the assistant next reads session context, then it reads the edited text, not the original.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 6.

### US-033 — Copy the settled answer in the RP language
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-030
- **Story:** As a roleplayer, I want to copy a settled answer with one click, so that I can paste it where the roleplay actually lives.
- **Acceptance criteria:**
  - **US-033.AC-1** — Given a settled answer entry exists, when the roleplayer copies it, then the instance places the answer's RP-language text on the clipboard.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### US-034 — Open a session with my own entry first
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-031
- **Story:** As a roleplayer, I want to open a session with my own answer first, so that I can start the roleplay myself instead of waiting for a partner block.
- **Acceptance criteria:**
  - **US-034.AC-1** — Given a session is open with no entries, when the roleplayer adds their own answer as the first entry, then the instance accepts it with no partner entry required before it.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 4.

### US-035 — An enormous paste warns but is never refused
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-027
- **Story:** As a roleplayer, I want to be warned about an enormous paste's context cost without being blocked, so that I stay in control of my own session.
- **Acceptance criteria:**
  - **US-035.AC-1** — Given a session is open, when the roleplayer pastes an enormous block of text, then the instance warns about its context cost.
  - **US-035.AC-2** — Given the paste triggered a context-cost warning, when the roleplayer proceeds, then the instance adds the entry regardless — the paste is never refused.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 4, round 9.

### US-109 — A partner block is edited in place and saved when focus leaves it; search reflects the new text
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-078
- **Story:** As a roleplayer, I want to edit a partner block right where it sits, so that I can fix a paste error without leaving the stream.
- **Acceptance criteria:**
  - **US-109.AC-1** — Given a partner block exists, when the roleplayer edits its text and moves focus away, then the instance saves the edit.
  - **US-109.AC-2** — Given a partner block was edited, when the assistant later calls `session_search`, then the search reflects the new text, not the original.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 12, round 13.

### US-110 — Any settled entry is edited in place and saved when focus leaves it; search reflects the new text
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-078
- **Story:** As a roleplayer, I want to edit any settled entry — partner block, turn, or decision — where it sits, so that fixing the record never means hunting for a separate edit screen.
- **Acceptance criteria:**
  - **US-110.AC-1** — Given any settled entry (partner block, turn, or decision) exists, when the roleplayer edits its text and moves focus away, then the instance saves the edit.
  - **US-110.AC-2** — Given any settled entry (partner block, turn, or decision) was edited, when the assistant later calls `session_search`, then the search reflects the new text, not the original.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 12, round 13; 2026-09-28, round 17.

### US-111 — Editing a partner block discards its cached translation
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-078
- **Story:** As a roleplayer, I want an edited partner block's translation to be re-done, so that I never see a stale translation of text that no longer exists.
- **Acceptance criteria:**
  - **US-111.AC-1** — Given a partner block has a cached translation, when the roleplayer edits the block's text, then the cached translation is discarded.
  - **US-111.AC-2** — Given the cached translation was discarded, when the roleplayer next flicks the block, then the instance translates the new text.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 12, round 13.

### US-112 — With no embedding model configured, an edit still saves, and the roleplayer is told search coverage is incomplete
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-078
- **Story:** As a roleplayer, I want my edit to succeed even when there is no embedding model, so that a platform gap never blocks my own record-keeping.
- **Acceptance criteria:**
  - **US-112.AC-1** — Given no embedding model is configured, when the roleplayer edits a settled entry, then the edit saves.
  - **US-112.AC-2** — Given no embedding model is configured, when the roleplayer's edit saves, then the roleplayer is told search coverage is incomplete.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 13.

### US-120 — The current zone's kind switch has two positions with an alternating default
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-081, UC-083
- **Story:** As a roleplayer, I want the kind switch to guess whether I'm pasting the partner or writing my own turn, so that I don't have to set it by hand every time.
- **Acceptance criteria:**
  - **US-120.AC-1** — Given the last partner-or-turn entry in the session was the roleplayer's own turn, when the roleplayer opens the current zone, then the switch defaults to partner.
  - **US-120.AC-2** — Given the last partner-or-turn entry in the session was a partner block, when the roleplayer opens the current zone, then the switch defaults to my turn.
- **_TBD:** what a settled decision does to the switch's alternating default was inferred, not confirmed.
- **Source:** `[inferred]` basis: round 17 states the default follows the last partner-or-turn entry, skipping decisions, but does not confirm a decision's own effect on the default; interview 2026-09-28, round 17.

### US-121 — A pasted partner block files itself immediately; double parentheses in partner text get no special treatment
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-027, UC-083
- **Story:** As a roleplayer, I want a pasted partner block to file itself with nothing to settle, so that pasting text I didn't compose never asks me to confirm it.
- **Acceptance criteria:**
  - **US-121.AC-1** — Given the current zone's switch is set to partner, when the roleplayer pastes the partner's text, then the instance files it as a partner entry immediately, with no Settle step.
  - **US-121.AC-2** — Given a pasted partner block contains double parentheses, when the instance files it, then the parenthesised text is stored as ordinary partner text with no OOC or instruction handling applied.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 4; 2026-09-28, round 17.

### US-122 — A settled decision sits in the record, reaches the assistant as context, and is found by session search
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-081
- **Story:** As a roleplayer, I want a settled decision to become part of what the assistant knows from then on, so that a tone or situation change actually sticks.
- **Acceptance criteria:**
  - **US-122.AC-1** — Given a decision is settled, when a later turn in the session is composed, then the decision's content is included in what the assistant is given.
  - **US-122.AC-2** — Given a decision is settled, when the assistant calls `session_search`, then the decision appears in the results.
- **Source:** `[confirmed: user]` interview 2026-09-28, round 17.

### US-123 — A settled decision offers no copy-out
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-081
- **Story:** As a roleplayer, I don't want a copy action on a decision, so that I'm not offered to post something that was never meant to leave the app.
- **Acceptance criteria:**
  - **US-123.AC-1** — Given a decision is settled, when the roleplayer views it, then no copy action is offered for it.
- **Source:** `[confirmed: user]` interview 2026-09-28, round 17.

### US-124 — Copying a settled turn yields plain text, not markdown
- **Actor:** ACT-002 · **Feature:** FEAT-009 · **Exercises:** UC-082
- **Story:** As a roleplayer, I want a copied turn in plain text, so that it pastes cleanly into an RP site that can't render markdown.
- **Acceptance criteria:**
  - **US-124.AC-1** — Given a settled turn contains markdown formatting, when the roleplayer copies it, then the clipboard holds plain text with no markdown syntax.
- **Source:** `[confirmed: user]` interview 2026-09-28, round 17.
<!-- product-spec:end -->
