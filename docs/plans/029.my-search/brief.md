# 029.my-search — My-search
<!-- roadmap:start -->
- **Stage:** 004.retrieval · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-017
- **Depends on:** `025.hybrid-search-port`, `008.app-shell-frame`

## Definition
Gives the roleplayer one box that reaches everything they own, from any screen. It is a different thing from the assistant's tools: those are content retrieval performed mid-discussion, this is the roleplayer finding the session they ran. Results are grouped by kind and never include another user's material. Unlike the assistant's reach, it applies no flag predicate at all — a note's state never filters a result out, and one that is currently disabled is shown marked as disabled, because re-enabling a note requires finding it first. A result jumps to the session or the entry it names. The box is reachable whether the left column is expanded or collapsed. This is the counterpart of `026.memo-search-tool`, which applies the opposite rule over the same notes — the two are deliberately asymmetric, not a bug to reconcile.

## Scope
**In:**
- the search route applying only the owner predicate
- results grouped by kind
- the disabled-note marking
- navigation from a result to its session or entry
- the trigger at the top of the tree and its duplicate on the collapsed rail

**Out:**
- the assistant's tools, which apply the opposite rule (`026`, `027`)
- maintaining the indexes (`024`)

## Open questions for the planner
- How a disabled hit is presented — the one part of this decision `search-and-retrieval.md` records as still open.
<!-- roadmap:end -->
