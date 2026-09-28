# 020.context-assembly — Context assembly
<!-- roadmap:start -->
- **Stage:** 003.assistant · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-010 (UC-033, UC-038, US-036, US-043, US-131), FEAT-012 (UC-045, US-054, US-055, US-098)
- **Depends on:** `015.memos`, `017.session-configuration`, `012.messages-and-settle`

## Definition
Decides exactly what the assistant is allowed to read, and in what order. The system prompt carries the resolved prompt plus every enabled forced note in the roleplayer's arranged order within the fixed level order, with the enabled flag gating first so a disabled note reaches the assistant by no path whatever its forced flag says. The message list is the union of the settled record and the current zone, so a settled decision is context from its point in time on while a settled discussion never reaches the assistant again. Language is handled here: the assistant mirrors the language of each message it answers, out-of-character exchanges happen in the preferred language, and candidates are always produced in the RP language. Because the record is mutable, the assistant always reads the current text.

## Scope
**In:**
- the system-prompt assembly with forced-note selection and ordering
- the message list as the union of the two views
- decisions as ordinary context
- the explicit exclusion list — buried discussion rows, disabled notes, translations, and anything outside the owning user
- the language instructions
- the parenthesis convention as a system-prompt responsibility
- the absence of any pruning, summarisation or token budget — a recorded product non-goal (`vision.md`), stated here as a deliberate absence, not an omission to fill in

**Out:**
- issuing the request and looping over tools (`021`)
- the tools themselves (`026`, `027`, `028`)
- the searchable half of notes (`026`)

## Open questions for the planner
None.
<!-- roadmap:end -->
