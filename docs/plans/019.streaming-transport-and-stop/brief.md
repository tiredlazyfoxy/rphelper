# 019.streaming-transport-and-stop — Streaming transport and stop
<!-- roadmap:start -->
- **Stage:** 003.assistant · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-010 (UC-085, US-132, US-133)
- **Depends on:** `006.llm-server-connections`, `013.stream-and-zone-ui`

## Definition
Builds the pipe the assistant's words travel down, and the brake. Streaming is a POST that answers with an event stream, consumed in the browser by reading the response body rather than through the native event-source API, because the request carries a JSON body and the roleplayer's text must never go in a URL. The application asserts its own non-buffering intent on the response so the requirement travels with it. A stop control replaces send while a generation is streaming and reaches any model work in flight — a generation, a tool call being waited on, or a translation — by aborting the request; whatever text had streamed is persisted as an ordinary candidate, no error is shown because nothing failed, and there is no iteration cap because the stop is what bounds a runaway loop.

## Scope
**In:**
- the event-frame protocol and its emitter, including the rule that an id in a frame is a decimal string
- the non-buffering response header
- the browser consumer built on a reader and decoder splitting frames on the blank line
- the abort path end to end
- the stop control occupying the send slot
- persisting partial assistant text on abort and reloading the zone to pick it up
- the four ways a stream ends

**Out:**
- what is actually generated (`021`)
- context assembly (`020`)
- the tool loop (`021`)
- the collapsible thinking and tool blocks (`022`)
- translation (`023`)

## Open questions for the planner
- How the server learns of the abort and what it does with an in-flight upstream request, given there is no stop request and the mechanism is the client dropping the connection.
<!-- roadmap:end -->
