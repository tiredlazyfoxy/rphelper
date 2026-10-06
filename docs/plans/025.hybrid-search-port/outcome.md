# Feature 025 — Hybrid search port · intended documentation changes

Planner section: the doc changes the architect applies once 025 ships. Grouped by target
file. "Un" / "Dn" refer to decisions in this folder's `context.md`.

## `docs/architecture/search-and-retrieval.md`

| Section | Intended change | Reason |
|---|---|---|
| The narrow port | Replace the bare signature with the as-built one: `search(connection, scope, query, limit, *, client_factory, timeout_seconds) -> list[SearchHit]`, in `services/search/hybrid.py`; the types (`SearchScope` variants, `SearchHit`) and pure helpers in `services/search/ports.py`. The embedding parameters exist because the vector arm embeds the query through 024's embedding service | U1, `004.context.md` |
| The narrow port | Record **three variants shipped in 025** — memo (vector + lexical, RRF), session (vector only), entry (lexical only, over `settled_entries` / `message_fts`) — and that the variant fixes the arms, so no caller chooses arms. **Characters and setups are not variants yet**: no index exists for them; `029`'s plan decides. Amend My-search's "five `SearchScope` variants" accordingly (three exist; two are `029`'s) | U1 |
| The narrow port | Record the **extra-predicate mechanism**: every variant requires `user_id` (the port applies `user_id = :user_id` itself, in every statement including hit hydration) and accepts an optional builder that, given the variant's base relation, returns a boolean clause ANDed with the owner predicate. That is how `026` (chain + `is_enabled AND NOT is_forced`, in R3's order) and `027` (`character_id`, `id != current`) bring their filters | U1, D6 |
| A memo hit is a snippet plus a level | **Correct "`scope`, plus the level's name"** to "`scope` and `scope_id`". The port does no name join; a caller that wants a level's name resolves it. Add the as-built snippet rule: lexical hits use FTS5 `snippet()` (plain text, no markers, `…`, 16 tokens); vector-only hits use a leading extract of `body` (whitespace collapsed, 160 characters, `…` when truncated) — the same plain-text shape | U3, D4 |
| The narrow port — `SearchHit` | Record the as-built shape: kind, id, fused score, snippet, plus memo `scope` / `scope_id` and entry `session_id`. **A session hit's snippet is none** — `sessions` has no text column; what a session result carries for the model is `027`'s decision | D3 |
| Reciprocal-rank fusion | As built: `k = 60`, per-arm depth 50, final count from the caller; a single-arm scope is fused over its one ranking so the score means the same everywhere; ties broken by ascending id. The `_TBD:` (no relevance data) stays open — all three numbers remain conventional | D1 |
| Query shape | Do **not** duplicate 024's outcome item: 024's `outcome.md` already records that step 2a is the forbidden pushed-down KNN form and must be rewritten. Apply that row; as built, 025 uses form (a) only (an exact scan ordered by `vec_distance_l2` over the candidate set, no `MATCH`) and does not use the over-fetching KNN alternative. Add: L2 is used; only rank reaches fusion, so the metric's scale is irrelevant | D5, `003.context.md` |
| Query shape | Add the **FTS query sanitising rule**: user text is split on whitespace, `"` removed, each token quoted as an FTS5 phrase, phrases OR-joined; no usable token → the lexical arm is skipped. User input can therefore never raise an FTS5 syntax error | `001.context.md` |
| Failure mode (or the port section) | Record the **query-side no-model rule**: whenever a variant's vector arm runs, the designated model is required — `no_embedding_model`, `secret_ref_missing` and `llm_unreachable` propagate unchanged; there is no lexical-only degrade (R4). An absent or empty vec / FTS table is **not** an error and yields no hits from that arm. The entry variant never opens the model. A vec table whose declared dimension differs from the designation raises `no_embedding_model` with `detail {"reason": "dimension_mismatch"}` before any provider call | U2, `003` |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| Layout — `services/search/` | As built: `ports.py` (contract + pure helpers), `candidates.py` (filters-first candidate selects), `lexical.py` (FTS5 arm), `vector.py` (vec0 arm), `hybrid.py` (`search`). `memo_search.py`, `session_search.py`, `my_search.py` remain to be added by `026`, `027`, `029` | `context.md` files list |
| Routers versus services | Record the deliberate service-to-service import: `services/search/vector.py` imports `services/embedding.py` | `003` |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Paths | Add the five `services/search/` modules | `context.md` files list |

## Flags for other owners

- **`026` / `027` (tools inside the compose loop).** `search` is **sync** and, on the
  vector arm, embeds through 024's `asyncio.run` bridge. Called from inside a running
  event loop (the compose loop is async) it would fail. The tool dispatch must run it off
  the loop (e.g. in a worker thread). Not decided here; the caller's plan owns it.
- **`026`.** R3's predicate order (`is_enabled` gates first, then `NOT is_forced`) is the
  caller's extra predicate; the port neither adds nor reorders it.
- **`027`.** Session hits carry no snippet; the tool decides what text represents a
  returned session to the model.
- **`029`.** Characters and setups need an index (and variants) before my-search can reach
  them; `session_fts` is still deferred (024 U7). The entry variant's snippet is plain
  text; highlighting, if wanted, is `029`'s change to the snippet markers.

## Observations

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B2 (the LLM/search/operations layer — `llm-and-streaming.md`, `search-and-retrieval.md`, `deployment.md`, `admin-surfaces.md`, `overview.md`).
Rejected items: none
Notes: Its instruction not to duplicate 024's forbidden-KNN row is honoured — the pushed-down form is recorded once, in `search-and-retrieval.md`, and the "Query shape" example's step 2a, which was exactly that form, is rewritten. Its `backend-structure.md` items were orphaned by the orchestrator's batching and applied in B2.
