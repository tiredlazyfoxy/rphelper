<!-- product-spec:start -->
# FEAT-017 — My search — use cases

### UC-058 — Search everything of mine from any screen
- **Actor:** ACT-002
- **Feature:** FEAT-017
- **Preconditions:** Roleplayer is authenticated.
- **Main flow:**
  1. Roleplayer opens the search box from any screen.
  2. Roleplayer enters a query.
  3. Instance searches across the roleplayer's own characters, setups, sessions, entries and memos.
- **Postconditions:** Results cover every kind of the roleplayer's own material.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7, round 8.

### UC-059 — Read results grouped by kind
- **Actor:** ACT-002
- **Feature:** FEAT-017
- **Preconditions:** A search has been run (UC-058).
- **Main flow:**
  1. Roleplayer views the results.
  2. Instance groups them by kind — character, setup, session, entry, memo.
- **Postconditions:** Roleplayer can scan results by kind rather than as one flat list.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 8.

### UC-060 — Jump from a result to the session or entry
- **Actor:** ACT-002
- **Feature:** FEAT-017
- **Preconditions:** Results are shown (UC-059).
- **Main flow:**
  1. Roleplayer selects a result.
  2. Instance opens the session or entry the result points to.
- **Postconditions:** Roleplayer lands on the exact session or entry, without re-locating it manually.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 8.
<!-- product-spec:end -->
