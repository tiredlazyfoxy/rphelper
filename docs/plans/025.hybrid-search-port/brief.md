# 025.hybrid-search-port — Hybrid search port
<!-- roadmap:start -->
- **Stage:** 004.retrieval · **Track:** multi-step · **Size:** M
- **Depends on:** `024.embedding-lifecycle`

## Definition
Builds the one way anything in this product searches. A query runs a vector arm and a lexical arm and the two result lists are fused by reciprocal rank, which is cheap because both indexes are in the same file. Relational filters run first and collapse the candidate set to hundreds before any vector work happens, which is the whole reason vectors live in the relational store. All of it sits behind one narrow port so the backing store can be swapped without touching a caller, and so the three tools and my-search cannot each grow their own query shape. A memo hit is identified by a snippet of its text and its level, because a note has no title.

## Scope
**In:**
- the port's interface
- the vector arm
- the lexical arm with its ranking
- reciprocal-rank fusion
- the query shape with its filters-first ordering
- the memo-hit shape as snippet plus level
- the owner predicate as a parameter the port requires rather than a caller's option

**Out:**
- every caller — `026`, `027`, `028` and `029` each bring their own filters and rules
- writing or maintaining any index (`024`)

## Open questions for the planner
- Whether the port exposes one method with a filter object or one per corpus, given `027` runs the vector arm only and `029` applies no flag predicate at all.
<!-- roadmap:end -->
