<!-- product-spec:start -->
# FEAT-014 — `memo_search` tool — use cases

### UC-051 — The assistant searches searchable memos across the session's chain
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-014
- **Preconditions:** Discussion is open (FEAT-010); the session's memo chain is resolved (UC-046).
- **Main flow:**
  1. Assistant calls the memo search tool during a discussion.
  2. Instance searches searchable memos across the session's resolved memo chain.
  3. Assistant receives matching memo content and continues composing.
- **Exception flows:**
  - The tool fails — the discussion continues; the assistant is told the tool failed and carries on without it.
- **Postconditions:** Works correctly with no setup level present in the chain.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5, round 9.

### UC-052 — Forced and disabled memos are excluded from results
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-014
- **Preconditions:** Discussion is open; the assistant calls the memo search tool.
- **Main flow:**
  1. Assistant calls the memo search tool.
  2. Instance excludes forced memos — already in context — and disabled memos — reaching the assistant by no path — from the results.
  3. Only searchable memos are returned.
- **Postconditions:** Results never include a forced or a disabled memo.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5.
<!-- product-spec:end -->
