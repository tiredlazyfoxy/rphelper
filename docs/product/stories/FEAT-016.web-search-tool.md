<!-- product-spec:start -->
# FEAT-016 — `web_search` tool — stories

### US-070 — Real-world fact lookup
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-016 · **Exercises:** UC-055
- **Story:** As a roleplayer, I want the assistant to look up real-world facts, so that details like a place, a weapon, a procedure or a period detail are accurate.
- **Acceptance criteria:**
  - **US-070.AC-1** — Given a discussion is open and the tool is enabled, when the assistant calls `web_search` for a real-world detail, then the instance returns the lookup result to the assistant.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 6.

### US-071 — Idiom / naturalness check
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-016 · **Exercises:** UC-056
- **Story:** As a roleplayer, I want the assistant to check whether a phrasing sounds natural or what an idiom means, so that my composed answer reads well in the RP language.
- **Acceptance criteria:**
  - **US-071.AC-1** — Given a discussion is open and the tool is enabled, when the assistant calls `web_search` to check whether a phrasing sounds natural or what an idiom means, then the instance returns the lookup result.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 6.

### US-072 — A direct user request to search
- **Actor:** ACT-002, ACT-004 · **Feature:** FEAT-016 · **Exercises:** UC-057
- **Story:** As a roleplayer, I want to directly ask the assistant to look something up, so that I can get an answer without leaving the discussion.
- **Acceptance criteria:**
  - **US-072.AC-1** — Given a discussion is open and the tool is enabled, when the roleplayer asks inside the discussion for something to be looked up, then the assistant calls `web_search` and relays the result in the discussion.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 6.

### US-073 — Disabled by the configuration chain
- **Actor:** ACT-002 · **Feature:** FEAT-016 · **Exercises:** UC-055
- **Story:** As a roleplayer, I want to be able to disable `web_search` through my configuration chain, so that I can turn it off wherever I don't want it available.
- **Acceptance criteria:**
  - **US-073.AC-1** — Given `web_search` is disabled by the session's resolved configuration chain, when a discussion is open, then the assistant cannot call `web_search` in that session.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 6.
<!-- product-spec:end -->
