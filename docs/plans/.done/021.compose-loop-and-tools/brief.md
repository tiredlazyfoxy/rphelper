# 021.compose-loop-and-tools — Compose loop and tools
<!-- roadmap:start -->
- **Stage:** 003.assistant · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-010 (UC-034, US-037, US-044)
- **Depends on:** `019.streaming-transport-and-stop`, `020.context-assembly`

## Definition
Makes the assistant actually answer. The roleplayer's message is persisted before any model call, so nothing they typed can be lost to a failure; the assembled context goes to the resolved model and a candidate streams back into the current zone in the RP language. The loop may call tools and come back any number of times before answering — there is no iteration cap — and a tool that fails does not end the exchange: the assistant is told and carries on without it. When the model goes away mid-discussion the entry and everything in the zone survive intact, the reason is shown, and a retry stays available at the exchange that failed. The three tools are declarations only here — the dispatch seam ships with nothing behind it; `026`, `027` and `028` fill it in stage 004.

## Scope
**In:**
- persisting the roleplayer's text before any outbound call
- the streaming completion call through the one client
- the tool-calling loop with its dispatch seam and the three tool definitions as declarations
- persisted tool rows
- the failed-tool path
- the failure paths including the model going away, with the reason transient and the retry persistent
- the ordering guarantee that protects the roleplayer's text

**Out:**
- every tool's implementation — `026`, `027` and `028` fill the seam
- the zone's rendering of thinking and tool blocks (`022`)
- translation (`023`)

## Open questions for the planner
- What the seam hands a tool and what it accepts back. Three stage-004 features (`026`, `027`, `028`) bind to this signature, and the owner scoping that makes isolation enforceable has to live in the seam itself rather than be re-implemented per tool.
<!-- roadmap:end -->
