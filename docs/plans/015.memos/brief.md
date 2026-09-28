# 015.memos — Memos
<!-- roadmap:start -->
- **Stage:** 002.record · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-012 (UC-042, UC-043, UC-044, UC-046, US-049, US-050, US-051, US-052, US-053, US-056, US-057, US-101, US-119)
- **Depends on:** `009.characters`, `010.setups`, `011.rp-sessions`

## Definition
Gives the roleplayer standing context that never has to be re-explained. A note is one body of markdown with no title, name or header field, created at any of four levels — user, character, setup, session — and edited with a live preview. Two independent flags govern it: enabled or disabled, and forced or not, and a disabled note keeps the forced flag it had so re-enabling restores it. A new note is enabled and not forced. A session's chain of notes resolves across all four levels and degrades correctly to three when the session has no setup, with no gap.

## Scope
**In:**
- the `memos` table with its scope and scope-id columns, the two boolean flags and the within-level sort key
- create, edit, flag-toggle and list routes scoped to the owning user
- the markdown editor with live preview
- chain resolution across the four levels including the no-setup case
- the reach statement a note carries (forced, searchable or disabled) with the enabled-gates-first ordering
- nothing persisted for an empty note

**Out:**
- the note wall and its cards, reordering and in-place edit — UC-075, UC-076, US-102, US-103, US-104 land with `016.note-wall`
- what a forced note does to the system prompt — UC-045, US-054, US-055, US-098 land with `020.context-assembly`
- reachability by the memo tool — US-099, US-100 land with `026.memo-search-tool`
- embedding a note (`024`)

## Open questions for the planner
- How the sort key is allocated and re-allocated within a level, since `016` will reorder against it.
- Where the user-level notes are edited before the settings screen exists in `017`.
<!-- roadmap:end -->
