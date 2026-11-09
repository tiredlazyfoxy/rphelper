# 027.session-search-tool — Session search tool
<!-- roadmap:start -->
- **Stage:** 004.retrieval · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-015
- **Depends on:** `025.hybrid-search-port`, `021.compose-loop-and-tools`, `011.rp-sessions`

## Definition
Lets the assistant remember what happened with this character before. It finds past sessions under the same character by meaning alone — no structured matching on a partner name or a setup, because the partner is free text and the setup is optional, and semantic matching is exactly what keeps the promise true when neither is recorded. A match weighs a session's entries together with its character's persona and its setup, which is what lets a query about a similar person find the right session rather than only a similar situation. Results never cross a character or a user boundary. A failure does not end the discussion.

## Scope
**In:**
- the tool's implementation behind the seam
- the vector arm only, with the lexical arm deliberately not enabled
- the character and owner predicates
- the three-source representation of a session in the match
- the result shape
- the failure result

**Out:**
- the lexical arm over the session index — deliberately not enabled here, since enabling it would reintroduce the structured partner-name matching FEAT-015 rejects; that index belongs to `029.my-search`
- the loop and the seam (`021`)
- maintaining the index (`024`)

## Open questions for the planner
- What a result carries so the assistant can use it — a summary, the matching entries, or a reference — which no product id fixes.
<!-- roadmap:end -->
