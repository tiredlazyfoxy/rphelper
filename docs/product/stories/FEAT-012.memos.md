<!-- product-spec:start -->
# FEAT-012 — Memos — stories

### US-049 — Memo at user level
- **Actor:** ACT-002 · **Feature:** FEAT-012 · **Exercises:** UC-042
- **Story:** As a roleplayer, I want to create a memo at the user level, so that it applies across every character and session I have.
- **Acceptance criteria:**
  - **US-049.AC-1** — Given the roleplayer is authenticated, when they choose the user level and save a memo, then the instance saves it at the user level.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5, round 6.

### US-050 — Memo at character level
- **Actor:** ACT-002 · **Feature:** FEAT-012 · **Exercises:** UC-042
- **Story:** As a roleplayer, I want to create a memo scoped to a character, so that it applies to every session under that character.
- **Acceptance criteria:**
  - **US-050.AC-1** — Given a character exists, when the roleplayer chooses the character level and saves a memo on it, then the instance saves it scoped to that character.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5, round 6.

### US-051 — Memo at setup level
- **Actor:** ACT-002 · **Feature:** FEAT-012 · **Exercises:** UC-042
- **Story:** As a roleplayer, I want to create a memo scoped to a setup, so that it applies to every session that reuses that setup.
- **Acceptance criteria:**
  - **US-051.AC-1** — Given a setup exists, when the roleplayer chooses the setup level and saves a memo on it, then the instance saves it scoped to that setup.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5, round 6.

### US-052 — Memo at session level
- **Actor:** ACT-002 · **Feature:** FEAT-012 · **Exercises:** UC-042
- **Story:** As a roleplayer, I want to create a memo scoped to a single session, so that it applies only there.
- **Acceptance criteria:**
  - **US-052.AC-1** — Given a session exists, when the roleplayer chooses the session level and saves a memo on it, then the instance saves it scoped to that session.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5, round 6.

### US-053 — A new memo defaults to enabled and not forced
- **Actor:** ACT-002 · **Feature:** FEAT-012 · **Exercises:** UC-042
- **Story:** As a roleplayer, I want a new memo to default to enabled and not forced, so that I don't have to set its state every time I just want it reachable.
- **Acceptance criteria:**
  - **US-053.AC-1** — Given the roleplayer creates a new memo at any level and sets no state explicitly, when it is saved, then it is enabled and not forced.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5, round 11, round 12.

### US-054 — An enabled, forced memo appears in the system prompt
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-012 · **Exercises:** UC-045
- **Story:** As a roleplayer, I want an enabled, forced memo to always reach the assistant, so that critical standing information is never missed or forgotten.
- **Acceptance criteria:**
  - **US-054.AC-1** — Given a memo is enabled and forced, when the roleplayer opens a session within the memo's scope, then the memo's content is included in what the assistant is given for every message in that session.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 11, round 12.

### US-055 — A disabled memo reaches the assistant by no path
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-012 · **Exercises:** UC-044
- **Story:** As a roleplayer, I want a disabled memo to be completely invisible to the assistant regardless of its forced flag, so that I can hold material the assistant should never see.
- **Acceptance criteria:**
  - **US-055.AC-1** — Given a memo is disabled, whatever its forced flag says, when a session within its scope is composed, then the memo's content is absent from the system prompt.
  - **US-055.AC-2** — Given a memo is disabled, whatever its forced flag says, when the assistant calls `memo_search` in that session, then the disabled memo is absent from the results.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 11, round 12.

### US-056 — Markdown with live preview
- **Actor:** ACT-002 · **Feature:** FEAT-012 · **Exercises:** UC-043
- **Story:** As a roleplayer, I want to write a memo in markdown with a live preview, so that I can format it while seeing exactly how it will render.
- **Acceptance criteria:**
  - **US-056.AC-1** — Given the roleplayer opens a memo for editing, when they write markdown content, then the instance renders a live preview as they write.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5.

### US-057 — The memo chain resolves with no setup present
- **Actor:** ACT-002 · **Feature:** FEAT-012 · **Exercises:** UC-046
- **Story:** As a roleplayer, I want the memo chain to resolve correctly when my session has no setup, so that going setup-free never costs me my memos.
- **Acceptance criteria:**
  - **US-057.AC-1** — Given a session has no setup, when the instance resolves the memo chain, then it degrades to user + character + session memos with no gap.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 6.

### US-098 — An enabled, forced note is in the system prompt for every request in that session
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-012 · **Exercises:** UC-075
- **Story:** As a roleplayer, I want an enabled, forced note in every request the session makes, so that the assistant never drops it mid-session.
- **Acceptance criteria:**
  - **US-098.AC-1** — Given a note is enabled and forced, when any message in its session is composed, then the note's content is included in what the assistant is given for that message.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 11, round 12.

### US-099 — An enabled, not-forced note is reachable only by `memo_search`
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-012 · **Exercises:** UC-075
- **Story:** As a roleplayer, I want an enabled, not-forced note reachable only when the assistant searches for it, so that background material doesn't cost context until it's relevant.
- **Acceptance criteria:**
  - **US-099.AC-1** — Given a note is enabled and not forced, when a session within its scope is composed, then the note's content is absent from the system prompt.
  - **US-099.AC-2** — Given a note is enabled and not forced, when the assistant calls `memo_search` in that session, then the note appears in the results.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 11, round 12.

### US-100 — A disabled note reaches the assistant by no path, whatever its forced flag says
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-012 · **Exercises:** UC-075
- **Story:** As a roleplayer, I want a disabled note to be completely invisible to the assistant no matter its forced flag, so that disabling always means fully hidden.
- **Acceptance criteria:**
  - **US-100.AC-1** — Given a note is disabled and forced, when a session within its scope is composed, then the note's content is absent from the system prompt.
  - **US-100.AC-2** — Given a note is disabled, when the assistant calls `memo_search` in that session, then the note is absent from the results.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 11, round 12.

### US-101 — Re-enabling a note restores the forced state it had when it was disabled
- **Actor:** ACT-002 · **Feature:** FEAT-012 · **Exercises:** UC-075
- **Story:** As a roleplayer, I want re-enabling a note to remember whether it was forced, so that I don't have to reconstruct its state from memory.
- **Acceptance criteria:**
  - **US-101.AC-1** — Given a forced note is disabled, when the roleplayer re-enables it, then it returns to forced with no further choice required.
  - **US-101.AC-2** — Given a not-forced note is disabled, when the roleplayer re-enables it, then it returns to not-forced with no further choice required.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 11, round 12.

### US-102 — Forced notes enter the system prompt in the roleplayer's arranged order within their level
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-012 · **Exercises:** UC-076
- **Story:** As a roleplayer, I want to control the order forced notes appear in within their level, so that I can put the most important ones first.
- **Acceptance criteria:**
  - **US-102.AC-1** — Given the roleplayer reorders two forced notes within the same level, when a session within that level's scope is composed, then the notes appear in the system prompt in the new order.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 11, round 12.

### US-103 — Levels keep a fixed order and a note cannot move between levels by dragging
- **Actor:** ACT-002 · **Feature:** FEAT-012 · **Exercises:** UC-076
- **Story:** As a roleplayer, I want the level order fixed and levels dragging-proof, so that reordering never accidentally rescopes a note.
- **Acceptance criteria:**
  - **US-103.AC-1** — Given notes exist at more than one level, when forced notes enter the system prompt, then they appear ordered user, then character, then session (setup ordered between character and session when present).
  - **US-103.AC-2** — Given the roleplayer drags a note toward a different level's group on the wall, when the drag ends, then the note remains at its original level.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 12; 2026-09-28, gap-closure round.

### US-104 — A note's text is edited where it sits and is saved when focus leaves it
- **Actor:** ACT-002 · **Feature:** FEAT-012 · **Exercises:** UC-075
- **Story:** As a roleplayer, I want to edit a note's text directly on its card, so that I don't have to open a separate screen for a quick change.
- **Acceptance criteria:**
  - **US-104.AC-1** — Given a note is showing on the wall, when the roleplayer edits its text and moves focus away, then the instance saves the edited text.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 12.

### US-119 — A note is one body of text, with no title, name or header field
- **Actor:** ACT-002 · **Feature:** FEAT-012 · **Exercises:** UC-043, UC-075
- **Story:** As a roleplayer, I want a note to be a single text body, so that I'm never forced to invent a title for something that doesn't need one.
- **Acceptance criteria:**
  - **US-119.AC-1** — Given the roleplayer creates or opens a note, when they look for a title or name field, then none exists — the note is a single text body, and any heading they want is markdown they type inside it.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 16.
<!-- product-spec:end -->
