# search

<!-- agent-ready:start -->

Hybrid search: the one narrow port every caller searches through (lexical FTS5 and vector arms fused by reciprocal rank), plus the memo, session and my-search corpora built on it — so no caller touches the index tables or the backing store directly.

## Glossary

**Files:**
- `__init__.py` — package marker; re-exports nothing, names are imported from their modules.
- `candidates.py` — filters first: turns a scope variant into the base relation and the owner-scoped candidate id select both arms rank inside.
- `hybrid.py` — the port's single entry point, `search`: arm selection, reciprocal-rank fusion, the limit and hit hydration.
- `lexical.py` — the lexical arm: BM25 ranking and a plain-text snippet over an FTS5 table.
- `memo_search.py` — searching a session's memo chain for notes the assistant can still be told about (`MEMO_SEARCH_LIMIT`, `searchable_chain_predicate`).
- `my_search.py` — the roleplayer's own search box across five kinds: characters and setups by case-folded substring outside the port (`_folded_contains` over the registered SQLite function `rp_casefold`, `LIKE` autoescape kept; the stored-name arm matches the same way), sessions, entries and memos through the port; sessions also get a stored-name arm (`search_session_names`) merged ahead of the vector hits (`merge_session_hits`), and session / entry hits carry the session name. Entry point `run_my_search`.
- `ports.py` — the port's contract: tuning constants, the scope variants (`SearchScope`), the `SearchHit` value and pure helpers.
- `session_search.py` — searching a character's past sessions for ones resembling what is being written now (the `session_search` tool's service half, `SESSION_SEARCH_LIMIT`).
- `vector.py` — the vector arm: embed the query once, then rank the candidate set by exact L2 distance over a `vec0` table.

See also: docs/architecture/search-and-retrieval.md

<!-- agent-ready:end -->
