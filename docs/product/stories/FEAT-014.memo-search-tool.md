<!-- product-spec:start -->
# FEAT-014 — `memo_search` tool — stories

### US-063 — Returns searchable memos from all four levels
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-014 · **Exercises:** UC-051
- **Story:** As a roleplayer, I want the assistant's memo search to reach every level of my memo chain, so that it can recall anything I've recorded, wherever I recorded it.
- **Acceptance criteria:**
  - **US-063.AC-1** — Given a session's memo chain includes searchable memos at the user, character, setup and session levels, when the assistant calls `memo_search`, then results include searchable memos from all four levels.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5, round 9.

### US-064 — Never returns another user's memos
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-014 · **Exercises:** UC-051
- **Story:** As a roleplayer, I want memo search results restricted to my own memos, so that my private material never leaks into another user's session.
- **Acceptance criteria:**
  - **US-064.AC-1** — Given the assistant calls `memo_search` inside a roleplayer's session, when results are returned, then no memo belonging to another user is ever included.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5.

### US-065 — Works when the session has no setup
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-014 · **Exercises:** UC-051
- **Story:** As a roleplayer, I want memo search to work correctly even when my session has no setup, so that going setup-free never breaks the assistant's recall.
- **Acceptance criteria:**
  - **US-065.AC-1** — Given a session has no setup, when the assistant calls `memo_search`, then results correctly include searchable memos from the user, character and session levels with no gap.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5, round 6.

### US-066 — A tool failure does not end the discussion
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-014 · **Exercises:** UC-051
- **Story:** As a roleplayer, I want a failed memo search to not stop the discussion, so that a single tool hiccup doesn't cost me the whole conversation.
- **Acceptance criteria:**
  - **US-066.AC-1** — Given the assistant calls `memo_search` and the tool fails, when the failure occurs, then the discussion continues and the assistant is told the tool failed.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5, round 9.
<!-- product-spec:end -->
