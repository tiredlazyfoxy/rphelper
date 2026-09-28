# 008.app-shell-frame — App shell frame
<!-- roadmap:start -->
- **Stage:** 002.record · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-020 (UC-070, UC-071, US-090, US-091, US-093)
- **Depends on:** `004.authentication-session`, `002.frontend-foundation`

## Definition
Gives the roleplayer the one screen they work in, as an empty frame. Three columns are laid out as a hand-written CSS grid with divider lines drawn by the grid gap itself; the left column collapses to a narrow icon rail and restores, and the collapse survives a reload. A user menu sits under the left column, opening upward, carrying logout and — only for an administrator — a link that navigates to the separate admin document. Below a narrow viewport threshold the left column becomes an off-canvas overlay. Nothing in the shell is resizable, by decision.

## Scope
**In:**
- `shell.css` with the three-column grid, the collapse class that re-points one custom property, and the responsive threshold
- the collapsed rail carrying create and expand
- the user menu with logout and the conditional admin link, absent rather than disabled for a roleplayer
- the layout-persistence module as a pure DOM-free record with per-field fallbacks that never throw and tolerate unknown stored keys
- the `app` entry's in-entry routing

**Out:**
- the tree's contents (`011`)
- the note wall (`016`)
- the stream (`013`)
- the settings screen behind the menu (`017`)
- my-search on the rail (`029`)
- the character page (`018`)

## Open questions for the planner
- Whether the collapsed rail's create action addresses characters only or is a menu, given `009` has not shipped when this does.
- Whether the off-canvas overlay below the threshold reuses the rail markup or is a third state.
<!-- roadmap:end -->
