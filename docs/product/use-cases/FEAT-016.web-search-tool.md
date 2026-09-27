<!-- product-spec:start -->
# FEAT-016 — `web_search` tool — use cases

### UC-055 — Look up a real-world fact
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-016
- **Preconditions:** Discussion is open (FEAT-010); the tool is enabled in the session's configuration chain (FEAT-013).
- **Main flow:**
  1. Assistant calls the web search tool during a discussion, to check a real-world detail — a place, a weapon, a procedure, a period detail.
  2. Instance returns the lookup result.
  3. Assistant uses it in composing.
- **Exception flows:**
  - The tool fails — the discussion continues; the assistant is told the tool failed and carries on without it.
- **Postconditions:** Discussion never blocked by a failed lookup.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 6, round 9.

### UC-056 — Check an idiom or whether phrasing sounds natural
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-016
- **Preconditions:** Discussion is open; the tool is enabled.
- **Main flow:**
  1. Assistant calls the web search tool to check whether a phrasing sounds natural, or what an idiom means.
  2. Instance returns the lookup result.
  3. Assistant uses it in composing.
- **Postconditions:** Result informs the candidate reply's wording.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 6.

### UC-057 — The roleplayer asks directly for a lookup
- **Actor:** ACT-002 (+ ACT-004)
- **Feature:** FEAT-016
- **Preconditions:** Discussion is open; the tool is enabled.
- **Main flow:**
  1. Roleplayer asks, inside the discussion, for something to be looked up.
  2. Assistant calls the web search tool.
  3. Instance returns the result to the assistant, which relays it in the discussion.
- **Postconditions:** Roleplayer sees the looked-up result in the discussion.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 6.
<!-- product-spec:end -->
