# 011.rp-sessions — RP sessions
<!-- roadmap:start -->
- **Stage:** 002.record · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-008 (UC-023, UC-024, UC-025, UC-026, US-026, US-027, US-028, US-029), FEAT-007 (UC-021, UC-022, US-024, US-025), FEAT-020 (UC-069, US-088, US-089)
- **Depends on:** `009.characters`, `010.setups`

## Definition
Gives the roleplayer the run itself. A session starts under a character, with a setup or with none, and there is no flow that makes choosing one a precondition. A session is always resumable and never finished; it is archived out of the working list and restored, and resuming a restored one works unchanged. Sessions appear in the tree beneath their character ordered by last use, with a setup shown as a label on the row rather than as a level of the tree. One setup can back several sessions at once.

## Scope
**In:**
- the `sessions` table with its character reference, nullable setup reference, owner column, `last_used_at` and `archived_at`
- start, resume, list, archive and restore routes scoped to the owning user
- the last-use ordering
- the tree's session level with the setup label
- the session's own empty screen

**Out:**
- the model captured at creation and the rest of the configuration chain (`017`)
- the session's stream, ruler and zone (`012`, `013`)
- notes at session level (`015`)
- starting a session by writing on the character page — UC-080, US-117 land with `018.character-page`

## Open questions for the planner
- What bumps `last_used_at` — opening, settling, or any write — since US-028's ordering is only as meaningful as that rule.
- Whether a session carries a title, given the FTS5 session index has a title column but no product id requires the roleplayer to set one.
<!-- roadmap:end -->
