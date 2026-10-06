# fast/005.degraded-embedding-path — Degraded embedding path
<!-- roadmap:start -->
- **Stage:** 006.repair · **Track:** fast · **Size:** S
- **Delivers:** FEAT-009 (US-112.AC-1 widened half, US-112.AC-3)
- **Depends on:** `024.embedding-lifecycle`, `032.privacy-isolation-audit`

## Definition
The roleplayer's own record-keeping never fails because the embedding side is broken, and a write that could not be embedded leaves no vector behind describing text the material no longer contains. Today the degraded path catches exactly two errors, so an unset `$ENV_VAR` API key makes a settle or a settled edit fail with a 500 and refuses the roleplayer's own text — the one thing US-112 exists to prevent. And a degraded write leaves the existing vector in place, so semantic search can still return material on the strength of superseded text. After this, any embedding-side failure degrades instead of refusing, and a degraded write clears the material's derived rows.

## Scope
**In:**
- every embedding-side failure reaching the degraded path rather than the caller, so the write commits and the roleplayer is told coverage is incomplete
- clearing the material's existing derived rows on a degraded write instead of leaving them in place

**Out:**
- the strict path, which is allowed to fail loudly and is unchanged
- recording *that* material is unembedded, and any staleness column — `024` U5 declined one and nothing here needs it
- the whole-index rebuild (`fast/002`), which is what later restores cleared material to semantic search

## Open questions for the planner
- `024` U5 decided a degraded write records nothing *and* leaves the vector in place. US-112.AC-3 reverses only the second half. Confirm the first half stands: nothing is recorded, and material simply drops out of semantic search until `fast/002` runs. `docs/product/features.md`'s Relationships section carries that as an accepted consequence.
- `032` found its one leak in exactly this shape — the `vec0` and FTS tables carry no user column, so every delete against them must resolve its row ids through an owner-scoped query first. Make that a stated constraint, and check whether `032`'s sweep left a helper to reuse.
- Widening the catch must stop short of swallowing programming errors. Decide the boundary — an embedding-side exception base type, or a named set — so a bug in the embedding code does not silently become "coverage incomplete".
<!-- roadmap:end -->
