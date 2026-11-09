# 016.note-wall — Note wall
<!-- roadmap:start -->
- **Stage:** 002.record · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-012 (UC-075, UC-076, US-102, US-103, US-104), FEAT-020 (UC-072, US-094, US-095)
- **Depends on:** `015.memos`, `008.app-shell-frame`, `013.stream-and-zone-ui`

## Definition
Puts the notes beside the stream where the roleplayer is writing. The wall opens over the stream as a flyout and can be pinned to become a real column, with the pin surviving a reload while merely being open does not. With no session open the wall is not shown at all. Notes are sticky-note cards grouped by level in the fixed chain order, each carrying two independent controls matching the two flags and a one-line statement of what it currently does. A note is edited where it sits and saved on focus loss, and reordered within its level by dragging — which changes what the system prompt will contain, so it must work from the keyboard too, and it can never cross a level boundary.

## Scope
**In:**
- the wall's two modes with their distinct positioning, the pinned mode as a grid column and the floating mode as an animated overlay
- the pin persisted in the layout record
- the not-shown-at-all case with no session
- the note cards with two icons, the struck-through disabled rendering that keeps the forced marker visible, and the reach line
- level headers in the fixed order
- in-place edit with blur-save
- reordering within a level with a keyboard sensor and a drop handler that refuses a cross-level move
- the revert to floating below the narrow threshold

**Out:**
- what a note does to the model's context (`020`)
- finding a note (`029`)
- the notes grid on the character page (`018`)
- any collapsing, filtering or search inside the wall, which is deliberately absent

## Open questions for the planner
None.
<!-- roadmap:end -->
