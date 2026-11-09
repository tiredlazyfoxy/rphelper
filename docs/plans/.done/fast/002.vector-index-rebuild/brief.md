# fast/002.vector-index-rebuild — Vector index rebuild
<!-- roadmap:start -->
- **Stage:** 004.retrieval · **Track:** fast · **Size:** S
- **Delivers:** FEAT-005 (UC-016, US-019)
- **Depends on:** `024.embedding-lifecycle`, `007.schema-drift-and-remediation`

## Definition
Closes the one part of the administrator's Database page that had nothing to act on until vectors existed. A button rebuilds the vector index from the rows themselves, which is the remedy after a changed embedding designation or a failed embedding on a write path — and it is the only surface for the operation, with no command-line equivalent, so one place owns it rather than two that can diverge. It is expensive in time and in metered calls, so it goes behind the shared confirm step.

## Scope
**In:**
- the rebuild route re-deriving every vector from its source rows
- the Database page's rebuild control with its confirm step and its progress or completion reporting

**Out:**
- any standalone script, explicitly declined
- prompting for a rebuild when the embedding designation changes, which deliberately neither forces nor prompts

## Open questions for the planner
None.
<!-- roadmap:end -->
