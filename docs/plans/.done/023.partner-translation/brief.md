# 023.partner-translation — Partner translation
<!-- roadmap:start -->
- **Stage:** 003.assistant · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-011, FEAT-009 (US-111)
- **Depends on:** `019.streaming-transport-and-stop`, `014.entry-editing-and-copy-out`, `017.session-configuration`

## Definition
Lets the roleplayer read their partner's text in the language they think in, without letting that reading reach the model. A partner entry carries a flicker that translates it into the preferred language on demand — nothing is translated until it is flicked — and flicking back shows the original. The result is cached after the first use so the second look is instant and costs nothing. A translation never enters session context, which holds only the RP language. A failed or stopped translation leaves the original showing with nothing cached, and a failure says why.

## Scope
**In:**
- the `translations` table keyed to the settled row
- the translate route
- the flicker control with its two states
- the cache read on a second flick
- the failure path showing the original with a visible error and caching nothing
- the stopped-translation path behaving identically
- discarding the cached translation when the partner block is edited, so the next flick re-translates the new text

**Out:**
- anything that would put a translation into context, which is forbidden
- translating the roleplayer's own turns or decisions

## Open questions for the planner
- Whether the translation is streamed into the flicker or awaited whole, given the stop must reach it either way.
<!-- roadmap:end -->
