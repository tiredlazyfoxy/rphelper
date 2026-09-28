# 026.memo-search-tool — Memo search tool
<!-- roadmap:start -->
- **Stage:** 004.retrieval · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-014, FEAT-012 (US-099, US-100)
- **Depends on:** `025.hybrid-search-port`, `021.compose-loop-and-tools`, `015.memos`

## Definition
Gives the assistant the searchable half of the roleplayer's standing notes. Mid-discussion it searches across the session's whole memo chain and gets back notes that are enabled and not forced — forced ones are excluded because they are already in the system prompt, and disabled ones because they reach the assistant by no path at all. It works correctly when the session has no setup, returning results from the three levels that do exist with no gap. It never returns another user's notes. A failure does not end the discussion: the assistant is told the tool failed and carries on. This is the counterpart of `029.my-search`, which applies the opposite rule over the same notes — the two are deliberately asymmetric, not a bug to reconcile.

## Scope
**In:**
- the tool's implementation behind the dispatch seam
- the chain-wide query with the enabled-and-not-forced predicate and the owner predicate
- the no-setup case
- the result shape as snippet plus level
- the failure result the loop reports to the assistant

**Out:**
- the loop and the seam (`021`)
- finding a note as the roleplayer (`029`)
- embedding notes (`024`)

## Open questions for the planner
- How many results the tool returns and whether the assistant can ask for more, which no product id fixes.
<!-- roadmap:end -->
