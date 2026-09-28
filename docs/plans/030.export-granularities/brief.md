# 030.export-granularities — Export granularities
<!-- roadmap:start -->
- **Stage:** 005.portability · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-018 (UC-061, UC-062, UC-063, UC-064 — export halves; US-080 — export half; US-077, US-078, US-079, US-081)
- **Depends on:** `011.rp-sessions`, `015.memos`, `012.messages-and-settle`, `010.setups`, `009.characters`

## Definition
Lets material leave the instance at four granularities, each carrying its own notes: the whole database, one user's own data, one character, and one session. The whole-database export is deliberately opaque to the administrator — the product offers no viewer, no search and no rendering of it, because it exists to move or restore an instance and not to read one. Vectors are not exported, since they are re-derivable. Credentials are not exported either, so a restored instance needs its environment supplied separately. A single-session export carries only that session's own notes, which means it arrives without the persona and setup that gave it meaning — a known and accepted consequence, not a defect.

## Scope
**In:**
- the envelope shape and its version marker
- the four export granularities and their boundaries
- the administrator's whole-database export on the Database page
- the roleplayer's own-data, character and session exports
- the exclusion of vectors and of secrets
- the opacity rule as an absence of any viewing surface

**Out:**
- import in every form (`031`)
- bringing an instance up from an export (`fast/003`)
- the cross-cutting privacy audit (`032`)

## Open questions for the planner
- The field-level detail of the envelope, which `overview.md` deliberately defers to this plan — `data-model.md` sketches it only.
- Whether a character export includes its sessions or only the character and its setups.
<!-- roadmap:end -->
