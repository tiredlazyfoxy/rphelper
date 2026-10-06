# Feature 026 — Memo search tool · intended documentation changes

Planner section: the doc changes the architect applies once 026 ships. Grouped by target
file. "Dn" refers to decisions in this folder's `context.md`.

## `docs/architecture/search-and-retrieval.md`

| Section | Intended change | Reason |
|---|---|---|
| `memo_search` — FEAT-014 | Record the **result count: at most 8, no paging**. The count is a named constant in `services/search/memo_search.py` passed to the port as `limit`. The tool declaration stays `query` only, so an assistant that wants more re-queries with different words. The fusion `_TBD:` (no relevance data for k / depth / count) stays open as a relevance question; 8 is conventional and user-confirmed, not measured | D1; closes 026 brief's open question |
| `memo_search` — FEAT-014 | Record **where the scope predicate lives**. The chain disjunction is one clause builder in `services/memo_chain.py`, beside `resolve_chain`, taking a relation and the level ids and omitting the setup term when there is no setup. `services/search/memo_search.py` builds the port's extra predicate as `is_enabled AND NOT is_forced AND <chain>`, `is_enabled` first. The port ANDs `user_id`. A test pins the R3 order on the compiled clause | D2 |
| `memo_search` — FEAT-014 | Record **what the model receives**. One line per hit in fused-rank order, `[<level>] <snippet>`, where `<level>` is the scope literal, the snippet's whitespace is collapsed so each hit is one line, and lines are joined by `\n`. No title, no character or setup name, no ids. Zero hits is a success with content `No matching notes.` The `tool_result` summary is `<N> memos` and never carries content | D4 |
| `memo_search` — FEAT-014 — Failure | Add that the tool **raises** and never builds its own failure outcome. `no_embedding_model`, `llm_unreachable` and `secret_ref_missing` propagate from the port, and arguments without a string `query` raise `tool_failed`. 021's seam turns any of them into the `tool_fail` frame and the "tool failed" model message. Proven through the real seam with no designated embedding model | D5 |
| `memo_search` — FEAT-014 | Record the **off-loop decision**, which closes 025's flag. The tool's async `run` calls the sync search through `asyncio.to_thread` on the connection the seam handed it. This is safe because the engine sets `check_same_thread=False` and the connection is used by one thread at a time. The worker thread has no running loop, so the port's `asyncio.run` embed bridge works there. `session_search` (027) faces the same constraint and can reuse the pattern | D3; 025 `outcome.md` "Flags for other owners" |
| A memo hit is a snippet plus a level | Confirm, for the tool surface, that the level reaches the model as the scope literal only. The tool resolves no level name, consistent with 025's correction of "plus the level's name" | D4; 025 U3 |
| The narrow port | Note the first caller: `memo_search` builds its memo scope from the seam's `ToolScope` ids only, and reads nothing but `query` from the tool arguments | D6 |

## `docs/architecture/llm-and-streaming.md`

| Section | Intended change | Reason |
|---|---|---|
| The tool-calling loop | The production registry is **no longer empty**. It holds `memo_search` (026), so with the session's switch on, `memo_search` is now offered in production. `session_search` and `web_search` remain unregistered until 027 / 028 | D3; supersedes 021's "production registry empty" |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| Layout — `services/search/` | Add `memo_search.py`: the result-count constant, the memo-search extra predicate and the sync `search_memos` | D3 |
| Layout — `services/tools/` | Add `memo_search.py`, the `memo_search` `Tool` adapter and its formatter. `seam.py`'s production registry now registers it | D3 |
| Layout — `services/memo_chain.py` | Note the public chain clause builder beside `resolve_chain` | D2 |
| Routers versus services | Record the service-to-service imports, none of which opens a transaction of its own. They are: `tools/memo_search.py` imports `search/memo_search.py`; `search/memo_search.py` imports `memo_chain.py` and the port; `tools/seam.py` imports `tools/memo_search.py` for registration. The adapter imports seam types for type-checking only, because the registry import would otherwise be a cycle | D2, D3 |

## `docs/architecture/domain-rules.md`

| Section | Intended change | Reason |
|---|---|---|
| R2 | Name the single home of the chain predicate, `memo_chain.py`'s clause builder, now shared by `resolve_chain`'s concern and `memo_search` | D2 |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Paths | Add `services/search/memo_search.py` and `services/tools/memo_search.py` | D3 |
| Invariants | `memo_search`: at most 8 hits; `is_enabled AND NOT is_forced` in R3 order; the sync port runs via `asyncio.to_thread` | D1–D3 |

## Plan supersessions (for the record, not architecture)

- 026 `002` amends three 021 test assertions that pinned the production registry as empty
  or the seam's import list as closed: 021 `004` DoD-2 and DoD-10 in `test_tool_seam.py`,
  and 021 `006` DoD-10 in `test_compose_route.py` (`002.context.md`).

## Observations

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B2 (the LLM/search/operations layer — `llm-and-streaming.md`, `search-and-retrieval.md`, `deployment.md`, `admin-surfaces.md`, `overview.md`).
Rejected items: none
Notes: Its `backend-structure.md` and `domain-rules.md` R2 items were orphaned by the orchestrator's batching and applied in B2. The registry's final three-tool state is written once rather than as its intermediate one-tool state.
