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
<!-- product-spec:end -->
