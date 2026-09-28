<!-- product-spec:start -->
# FEAT-017 — My search — stories

### US-074 — Find a session by a half-remembered detail
- **Actor:** ACT-002 · **Feature:** FEAT-017 · **Exercises:** UC-058
- **Story:** As a roleplayer, I want to search everything of mine from one search box, so that I can find a session or entry by a half-remembered detail without knowing where it lives.
- **Acceptance criteria:**
  - **US-074.AC-1** — Given the roleplayer opens the search box from any screen, when they enter a query describing a half-remembered detail, then the instance returns matching results from across their characters, setups, sessions, entries and memos.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7, round 8.

### US-075 — Results grouped by kind
- **Actor:** ACT-002 · **Feature:** FEAT-017 · **Exercises:** UC-059
- **Story:** As a roleplayer, I want search results grouped by kind, so that I can scan characters, setups, sessions, entries and memos separately.
- **Acceptance criteria:**
  - **US-075.AC-1** — Given a search has been run, when the roleplayer views the results, then they are grouped by kind — character, setup, session, entry, memo.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 8.

### US-076 — Results never include another user's material
- **Actor:** ACT-002 · **Feature:** FEAT-017 · **Exercises:** UC-058
- **Story:** As a roleplayer, I want my search results restricted to my own material, so that another user's characters, sessions or memos never appear.
- **Acceptance criteria:**
  - **US-076.AC-1** — Given the roleplayer runs a search, when results are returned, then no result belonging to another user is ever included.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7, round 8.

### US-118 — My search is reachable whether the left column is expanded or collapsed
- **Actor:** ACT-002 · **Feature:** FEAT-017 · **Exercises:** UC-058
- **Story:** As a roleplayer, I want the search box reachable in both states of the left column, so that collapsing it for space never costs me the search I might need next.
- **Acceptance criteria:**
  - **US-118.AC-1** — Given the left column is expanded, when the roleplayer looks for the search box, then it is reachable.
  - **US-118.AC-2** — Given the left column is collapsed to an icon rail, when the roleplayer looks for the search trigger, then it is reachable from the rail.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7, round 8, round 14, round 15.

### US-137 — My-search returns disabled memos, marked as disabled
- **Actor:** ACT-002 · **Feature:** FEAT-017 · **Exercises:** UC-058, UC-059
- **Story:** As a roleplayer, I want a disabled or not-forced memo to still turn up in my own search, so that I can find and manage it even when the assistant can't reach it.
- **Acceptance criteria:**
  - **US-137.AC-1** — Given memos exist that are disabled or not forced, when the roleplayer searches, then they are returned like any other memo — note state never filters results.
  - **US-137.AC-2** — Given a returned memo is currently disabled, when the roleplayer views the results, then it is shown as disabled.
- **Source:** `[confirmed: user]` interview 2026-09-28, gap-closure round.
<!-- product-spec:end -->
