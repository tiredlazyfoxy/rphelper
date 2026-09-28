# 022.discussion-ui — Discussion UI
<!-- roadmap:start -->
- **Stage:** 003.assistant · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-010 (UC-032, UC-035, UC-036, UC-079, US-038, US-039, US-040, US-113, US-114, US-116)
- **Depends on:** `021.compose-loop-and-tools`, `013.stream-and-zone-ui`

## Definition
Makes working with the assistant something the roleplayer can see and do. A discussion is opened on the answer being worked out and is followed inline beneath it in the same stream rather than in a separate panel. The assistant's tool calls and thinking are visible while it works and tuck themselves away when it finishes, staying re-openable because they are real rows and not transient UI. A candidate is promoted, rewritten or replaced entirely before settling. Settling collapses the discussion in place; a collapsed one stays readable but can never be edited, and re-opening it succeeds only while it is still the last thing, as an undo for a mis-click rather than a workflow.

## Scope
**In:**
- opening a discussion on an answer
- the inline placement beneath the answer it belongs to
- live assistant messages rendering as they stream
- the collapsible thinking and tool blocks, open while working and tucked away after
- promote, edit and write-from-scratch in the zone
- the collapse on settle and the readable collapsed rendering
- the refusal to edit a collapsed discussion
- the transient failure notice and the persistent retry rendered at the failed exchange

**Out:**
- the server's settle and re-open rules and their success and refusal cases — US-041 and US-042 are `012`'s; the re-open affordance itself is `013`'s
- context (`020`)
- the stop control (`019`)

## Open questions for the planner
None.
<!-- roadmap:end -->
