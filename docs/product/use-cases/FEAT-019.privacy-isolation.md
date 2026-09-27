<!-- product-spec:start -->
# FEAT-019 — Privacy & isolation — use cases

### UC-065 — Every listing, search and tool is scoped to the owning user
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-019
- **Preconditions:** Roleplayer is authenticated.
- **Main flow:**
  1. Roleplayer, or the assistant acting in their session, lists, searches, or invokes a tool.
  2. Instance scopes the result set to material owned by that user alone.
- **Postconditions:** No listing, search result or tool result ever names another user's material.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 1, round 2.

### UC-066 — Administrative surfaces expose no user content
- **Actor:** ACT-001
- **Feature:** FEAT-019
- **Preconditions:** Administrator is authenticated.
- **Main flow:**
  1. Administrator uses an administrative surface — account list, connections, drift report, whole-database export.
  2. Instance shows administrative data only — no character, session, setup or memo content.
- **Postconditions:** No administrative surface, at any time, shows a user's RP content.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 1, round 2.
<!-- product-spec:end -->
