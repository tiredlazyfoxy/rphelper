# 014.entry-editing-and-copy-out — Entry editing and copy-out
<!-- roadmap:start -->
- **Stage:** 002.record · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-009 (UC-029, UC-030, UC-078, UC-082, US-032, US-033, US-035, US-109, US-110, US-124)
- **Depends on:** `013.stream-and-zone-ui`

## Definition
Makes the settled record mutable forever and gets text back out to where the roleplay actually happens. Any settled entry — a partner block, a turn or a decision — is edited where it sits in the stream and saved when focus leaves it, including one from weeks ago. A settled turn is copied out as plain text rather than markdown, ready to paste into Discord or an RP site; a settled decision offers no copy at all. An enormous paste warns about what it will cost in context but is never refused.

## Scope
**In:**
- the edit-text route for a settled row
- in-place editing with blur-save in the stream for all three kinds
- the copy-out control on a turn and its absence on a decision
- plain-text rather than markdown on copy
- the client-side context-cost warning on a large paste, which never blocks the paste

**Out:**
- discarding a partner block's cached translation on edit — US-111 lands with `023.partner-translation`
- the incomplete-search-coverage notice — US-112 lands with `024.embedding-lifecycle`
- re-indexing an edited row (`024`)
- editing a collapsed discussion, which is forbidden (`022`)

## Open questions for the planner
- At what size the paste warning fires, which no product id or architecture doc fixes — only that it is a warning and never a refusal.
- Whether an edit to a settled row touches `last_used_at`.
<!-- roadmap:end -->
