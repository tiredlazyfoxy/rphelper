# 009.characters — Characters
<!-- roadmap:start -->
- **Stage:** 002.record · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-006
- **Depends on:** `008.app-shell-frame`

## Definition
Gives the roleplayer the persona the assistant will one day compose as. A character is created, its persona sheet edited, and it appears in a list that is the roleplayer's alone — no screen shows another user's characters. A character is archived out of the working list and restored from it; nothing is ever destroyed. The character level of the left column's tree appears here, so a character is reachable from the shell as soon as it exists.

## Scope
**In:**
- the `characters` table with its owner column and `archived_at`
- create, edit-persona, list, archive and restore routes, each scoped to the owning user
- a character screen showing the persona and the character's own sessions area
- the tree's character level
- the archived/working-list distinction in both the tree and the list

**Out:**
- setups (`010`)
- sessions (`011`)
- notes at character level (`015`)
- the character's resolved configuration (`017`)
- the full character page with its notes grid, setups and composer (`018`)
- the draft-page creation flow (`018`)

## Open questions for the planner
- Whether the persona is one markdown body or a set of fields, which `docs/product/` does not fix and `data-model.md` leaves as shape.
- Whether an archived character's sessions stay reachable directly.
<!-- roadmap:end -->
