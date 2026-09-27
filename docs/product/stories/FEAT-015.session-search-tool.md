<!-- product-spec:start -->
# FEAT-015 — `session_search` tool — stories

### US-067 — Finds a past session with a similar person or situation
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-015 · **Exercises:** UC-053
- **Story:** As a roleplayer, I want the assistant to find a past session about a similar person or situation, so that it can draw on history I don't have to re-explain.
- **Acceptance criteria:**
  - **US-067.AC-1** — Given the roleplayer has other sessions under the same character, when the assistant calls `session_search`, then it returns a past session with a similar person or situation by meaning.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, challenge C5.

### US-068 — Purely semantic — works with no setup and no partner field
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-015 · **Exercises:** UC-053
- **Story:** As a roleplayer, I want session search to work by meaning alone, so that it still finds a similar past session even when neither session has a setup or a recorded partner.
- **Acceptance criteria:**
  - **US-068.AC-1** — Given neither the current session nor a past session under the same character has a setup or a recorded partner field, when the assistant calls `session_search`, then it still finds the past session by matching its content by meaning.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, challenge C5.

### US-069 — Never crosses a character or user boundary
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-015 · **Exercises:** UC-054
- **Story:** As a roleplayer, I want session search results confined to the current character and to me, so that another character's or another user's sessions never surface.
- **Acceptance criteria:**
  - **US-069.AC-1** — Given the assistant calls `session_search`, when results are returned, then no session belonging to a different character is ever included.
  - **US-069.AC-2** — Given the assistant calls `session_search`, when results are returned, then no session belonging to a different user is ever included.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5.
<!-- product-spec:end -->
