<!-- product-spec:start -->
# FEAT-015 — `session_search` tool — use cases

### UC-053 — The assistant finds past sessions under the same character by meaning
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-015
- **Preconditions:** Discussion is open (FEAT-010); the roleplayer has other sessions under the same character.
- **Main flow:**
  1. Assistant calls the session search tool during a discussion.
  2. Instance searches the roleplayer's past sessions under the same character, by meaning, for a similar person or situation.
  3. Assistant receives matching session content and continues composing.
- **Exception flows:**
  - The tool fails — the discussion continues; the assistant is told the tool failed and carries on without it.
- **Postconditions:** Semantic only — no structured matching on partner name or setup; works with no setup and no partner field present on either session.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 9, challenge C5.

### UC-054 — Results never leave the character or the user
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-015
- **Preconditions:** Assistant calls the session search tool.
- **Main flow:**
  1. Assistant calls the session search tool.
  2. Instance restricts results to sessions under the same character, owned by the same user.
  3. No session belonging to another character or another user is ever returned.
- **Postconditions:** Search boundary matches FEAT-019.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5.
<!-- product-spec:end -->
