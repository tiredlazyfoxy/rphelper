# 028.web-search-tool — Web search tool
<!-- roadmap:start -->
- **Stage:** 004.retrieval · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-016
- **Depends on:** `021.compose-loop-and-tools`, `017.session-configuration`

## Definition
Lets the assistant look something up in the real world on the roleplayer's behalf. Three uses justify it: a real-world fact such as a place, a weapon, a procedure or a period detail; an idiom or naturalness check on whether a phrasing sounds right; and a direct request from the roleplayer to go and look. Like any other tool it is switched on or off by the configuration chain, and a failure does not end the discussion. The provider sits behind an adapter so the seam is what the product depends on rather than any one search service.

## Scope
**In:**
- the tool's implementation behind the seam
- the provider adapter and one concrete provider
- the configuration switch honoured at call time
- the failure result
- the three justified uses reflected in the tool's description to the assistant

**Out:**
- anything that would send the roleplayer's own material outbound beyond the query itself
- caching results

## Open questions for the planner
- Which provider, and what its credential looks like, since `overview.md` deliberately specifies the seam and not the adapter — and whether the credential follows the same environment-pointer convention as a model server's.
<!-- roadmap:end -->
