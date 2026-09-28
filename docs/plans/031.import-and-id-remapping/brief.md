# 031.import-and-id-remapping — Import and id remapping
<!-- roadmap:start -->
- **Stage:** 005.portability · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-018 (UC-061, UC-062, UC-063, UC-064 — import halves; US-080 — import half; US-082, US-136)
- **Depends on:** `030.export-granularities`

## Definition
Lets an export come back in, at the same four granularities, without ever colliding with what is already there. Imported material arrives under fresh identity: the importer mints new identifiers and remaps every internal reference in the payload, so nothing can overwrite or merge into an existing row. It always merges as new items alongside what exists, which means importing the same export twice yields duplicates and nothing warns about that — an accepted consequence, not a missing feature. An imported session arrives without the character and setup context it referred to, per the known and accepted consequence recorded against the export side.

## Scope
**In:**
- the four import granularities
- identifier re-minting and reference remapping across the payload
- merge-as-new semantics
- the administrator's whole-database import and the roleplayer's three
- validation and the typed failure of a malformed or incompatible envelope
- re-deriving vectors for imported rows or leaving them to the rebuild

**Out:**
- warning about a duplicate import, explicitly not done
- the bootstrap path that uses this (`fast/003`)

## Open questions for the planner
- Whether imported rows are embedded during the import or left for `fast/002`'s rebuild, which decides whether an import needs an embedding model configured.
<!-- roadmap:end -->
