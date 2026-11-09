# 010.setups — Setups
<!-- roadmap:start -->
- **Stage:** 002.record · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-007 (UC-020, UC-068, US-023, US-087)
- **Depends on:** `009.characters`

## Definition
Gives a character a reusable description of a situation that several sessions can share. A setup is created under a character, carries its own text, and is archived out of the working list and restored, exactly as a character is. It is genuinely optional — this feature adds the object and its lifecycle, and deliberately adds no flow that requires choosing one.

## Scope
**In:**
- the `setups` table with its character reference, owner column and `archived_at`
- create, edit, list, archive and restore routes scoped to the owning user
- a setups list under the character with its editor

**Out:**
- starting a session with or without a setup, and reusing one setup across several sessions — UC-021, UC-022, US-024, US-025 are delivered by `011.rp-sessions`, because a setup's use is a session concern
- notes at setup level (`015`)
- the setup label on a session row in the tree (`011`)
- the setups block on the character page (`018`)

## Open questions for the planner
- Whether archiving a setup that sessions reference is refused, warned about, or silent, given R6 forbids destruction but says nothing about referenced rows.
<!-- roadmap:end -->
