# 024.embedding-lifecycle — Embedding lifecycle
<!-- roadmap:start -->
- **Stage:** 004.retrieval · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-009 (US-112)
- **Depends on:** `012.messages-and-settle`, `015.memos`, `006.llm-server-connections`, `014.entry-editing-and-copy-out`

## Definition
Keeps the searchable shadow of the roleplayer's material in step with the material itself. Vector tables and full-text tables live in the same database file as the rows they describe, so a vector write commits in the same transaction as the relational write that caused it. Every write path that changes searchable text re-embeds what it changed, including the fan-out where one edit invalidates a session's own representation because a session is represented by its entries together with its character's persona and its setup. Toggling a note's flags is one row updated with no vector work at all. With no embedding model configured an edit still saves and the roleplayer is told search coverage is incomplete — never refused.

## Scope
**In:**
- the vector tables and their dimensions
- the full-text tables
- the embedding call through the designated server and model
- the embed-on-write paths for notes, entries and sessions
- the invalidation fan-out from an entry edit to its session's representation
- the no-vector-work-on-toggle guarantee
- the incomplete-coverage notice when no embedding model is designated
- the deliberate asymmetry between the two write paths' failure handling

**Out:**
- querying (`025`)
- any tool (`026`, `027`, `028`)
- my-search (`029`)
- the administrator-triggered rebuild (`fast/002`)

## Open questions for the planner
- How a failed embedding on a write path is recorded so the rebuild can find it later, given a failure must not fail the write.
- What the sparse-rowid verification item resolves to in the vector tables.
<!-- roadmap:end -->
