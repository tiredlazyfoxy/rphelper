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

### US-053 — A new memo defaults to searchable
- **Actor:** ACT-002 · **Feature:** FEAT-012 · **Exercises:** UC-042
- **Story:** As a roleplayer, I want a new memo to default to searchable, so that I don't have to set its state every time I just want it reachable.
- **Acceptance criteria:**
  - **US-053.AC-1** — Given the roleplayer creates a new memo at any level and sets no state explicitly, when it is saved, then its state is `searchable`.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5.

### US-054 — A forced memo appears in the system prompt
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-012 · **Exercises:** UC-045
- **Story:** As a roleplayer, I want a forced memo to always reach the assistant, so that critical standing information is never missed or forgotten.
- **Acceptance criteria:**
  - **US-054.AC-1** — Given a memo's state is `forced`, when the roleplayer opens a session within the memo's scope, then the forced memo's content is included in what the assistant is given for every message in that session.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5.

### US-055 — A disabled memo reaches the assistant by no path
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-012 · **Exercises:** UC-044
- **Story:** As a roleplayer, I want a disabled memo to be completely invisible to the assistant, so that I can hold material the assistant should never see.
- **Acceptance criteria:**
  - **US-055.AC-1** — Given a memo's state is `disabled`, when a session within its scope is composed, then the memo's content is absent from the system prompt.
  - **US-055.AC-2** — Given a memo's state is `disabled`, when the assistant calls `memo_search` in that session, then the disabled memo is absent from the results.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5.

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
<!-- product-spec:end -->
