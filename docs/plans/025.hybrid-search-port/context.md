# Feature 025 — Hybrid search port · feature-wide context

## What this feature is

025 builds the one way anything in this product searches: a single `search` entry point
behind a narrow port. A query runs a vector arm and/or a lexical arm over a candidate set
that relational filters have already collapsed, and the arms' rankings are fused by
reciprocal rank. The agreed boundary is `brief.md` in this folder (Definition, Scope
In/Out). **Out:** every caller (`026` memo_search, `027` session_search, `028`, `029`
my-search) and every index write (`024`). 025 creates no table, writes no row and adds no
route.

**Delivers:** no product id directly (the brief has no `Delivers:` line). The port is the
mechanism later features bind to. Ids that genuinely constrain it are cited where a DoD
exercises them:

| Constraint | Source | Where it lands |
|---|---|---|
| A memo has no title; a memo hit is snippet + level | US-119 | `001` (hit shape), `004` |
| Search never crosses the user boundary | UC-065, US-085 | `002` (candidates), `004` |
| Zone / buried messages are not findable as entries | US-115, UC-038, R11 | `002` (entry candidates read `settled_entries`) |
| No embedding model → error, never substitution | R4 (`llm-and-streaming.md`) | `003`, `004` |

## Build prerequisite — 024 must be delivered first

**024 (`docs/plans/024.embedding-lifecycle/`) is planned but not built.** 025 builds on top
of it and must not start until 024's steps `001` and `002` are `done`. 025 binds to these
024 names (planned; where 024's `## Skeleton` freezes a different exact name, 025's
skeleton binds to the frozen one):

- `app/db/search_tables.py` — the four table-name constants (`memo_fts`, `message_fts`,
  `memo_vec`, `session_vec`), `vector_table_dimension(connection, name)` (None when the
  table is absent), and, for test setup only, `ensure_fts_tables` / `ensure_vector_tables`.
- `app/services/embedding.py` — `open_embedding_model(connection, client_factory,
  timeout_seconds)` → `EmbeddingModelHandle` (model name, `embedding_dim`, client);
  `embed_texts(handle, texts)` → one vector per text, one provider call;
  `DEFAULT_EMBED_TIMEOUT_SECONDS`; `write_vector` (test setup only).
- `backend/tests/llm_fakes.py` — the deterministic fake embedder and fake factory (024
  `context.md` "Test conventions"). 025 tests reuse it and never edit it.
- Errors (from `errors.py`, unchanged): `NoEmbeddingModelError` (`no_embedding_model`,
  409; `detail {"reason": "dimension_mismatch"}` for a dimension mismatch, 024 D8),
  `LlmUnreachableError` (`llm_unreachable`, 502), and the `secret_ref_missing` error.

024's table facts 025 depends on: `memo_fts(body)` external content on `memos`,
`message_fts(text)` external content on `messages` holding **record rows only** (via
triggers), `memo_vec(memo_id, embedding)`, `session_vec(session_id, embedding)`, all keyed
by snowflake ids. There is **no `session_fts`**. The tables live outside `schema.metadata`.

## Architecture this binds to

- `search-and-retrieval.md`: "Hybrid search", "Reciprocal-rank fusion", "The narrow port",
  "A memo hit is a snippet plus a level", "Query shape", "The sparse-rowid verification
  item", and the `session_search` "vector arm only" decision.
- `backend-structure.md`: Layout (`services/search/ports.py`, `services/search/hybrid.py`),
  services import no `fastapi`.
- `data-model.md`: `memos`, `sessions`, `messages` and the `settled_entries` view;
  Identifiers (snowflake ids).
- `domain-rules.md`: R4 (no substitution), R5 (owner scope in SQL), R11 (readers go
  through the views).
- 024 `outcome.md` row "The sparse-rowid verification item" (the forbidden KNN form and
  the two correct forms).

Cited, never copied.

## Files this feature touches

```
backend/app/services/search/
  __init__.py      # NEW — empty package marker                                  (001)
  ports.py         # NEW — scope variants, SearchHit, RRF, FTS sanitiser,
                   #       leading extract, constants. Pure, no DB.               (001)
  candidates.py    # NEW — filters-first candidate id select per scope variant    (002)
  lexical.py       # NEW — BM25 + snippet over memo_fts / message_fts             (002)
  vector.py        # NEW — query embedding + exact scan over memo_vec/session_vec (003)
  hybrid.py        # NEW — search(): arm selection, fusion, limit, hydration      (004)
```

**Not touched — a step that touches one is out of scope:** `db/schema.py`,
`db/search_tables.py`, `db/engine.py`, `services/embedding.py`, `services/memos.py`,
`errors.py`, `dependencies.py`, any router, `main.py`, `tests/conftest.py`,
`tests/llm_fakes.py`. No new Python dependency.

## User-confirmed decisions (binding)

### U1 — One port method, typed scope variants

One `search` entry point, taking a connection first, a scope, the query text and a limit,
plus keyword-only `client_factory` and `timeout_seconds` (defaults: the real client
factory and `DEFAULT_EMBED_TIMEOUT_SECONDS`, the 024 D9 pattern). It returns an ordered
list of `SearchHit`.

There is one scope variant per **indexed** corpus, and the variant fixes which arms run:

| Variant | Base (candidate) relation | Vector arm | Lexical arm |
|---|---|---|---|
| memo | `memos` | `memo_vec` | `memo_fts` |
| session | `sessions` | `session_vec` | — (no `session_fts`; `027` forbids it anyway) |
| entry | `settled_entries` view (R11) | — | `message_fts` |

- **Every variant requires `user_id`.** It cannot be constructed without one. The port
  always applies `<base>.user_id = :user_id` itself; it is not a caller option (brief
  Scope In; `search-and-retrieval.md` "The narrow port").
- **Every variant accepts an optional caller-supplied extra predicate** over its base
  relation. It is a builder: given the base relation the port uses as its FROM object, it
  returns a SQLAlchemy boolean clause over that relation's columns. The port ANDs it with
  the owner predicate. Examples of future use: `026`'s chain plus `is_enabled AND NOT
  is_forced`; `027`'s `character_id = :c AND id != :current`.
- Characters and setups are **not** corpora in 025 (no index exists; `029`'s plan decides).

### U2 — No embedding model propagates; absent tables are empty, not errors

- When a scope's vector arm runs, the port opens the model through 024's
  `open_embedding_model` and lets `NoEmbeddingModelError`, `secret_ref_missing` and
  `LlmUnreachableError` propagate unchanged. No degrade to lexical-only, no substitution
  (R4). Callers convert (e.g. to `tool_fail`).
- An **absent or empty vec table** yields no vector hits and is not an error. An **absent
  FTS table** yields no lexical hits and is not an error. (Pre-024-bootstrapped instances
  lack these until a qualifying write or the rebuild — 024 D2.)
- The model is opened **only** when the vector arm runs. The entry scope never touches it.

### U3 — A memo hit's level is `scope` + `scope_id` only

No name join. Callers that want a level's name resolve it themselves. This deviates from
`search-and-retrieval.md`'s "scope, plus the level's name"; `outcome.md` records the
correction.

## Planner / orchestrator decisions

### D1 — Fusion (conventional, per the architecture's `_TBD:` on k / depth / count)

- RRF score `Σ 1 / (k + rank)` over the arms that ran, `rank` 1-based, `k = 60`. Rank
  only; raw distances and BM25 scores are never mixed.
- Fusion is **within one corpus** — a single `search` call covers one scope; there is no
  cross-kind ranking.
- A single-arm scope (session, entry) still goes through the same fusion over its one
  ranking, so `score` has one meaning everywhere.
- **Ties** in fused score are broken by ascending id, so output is deterministic.
- **Per-arm candidate depth** is a module constant, **50**. The final count is the
  caller's `limit`.
- Constants live in `ports.py`: `RRF_K = 60`, `ARM_DEPTH = 50`, `SNIPPET_CHARS = 160`
  (exact names frozen by the skeleton). All three are conventional, not measured.

### D2 — Early exits

`limit <= 0`, or a query that is empty or whitespace-only, returns `[]` with **no**
embedding model opened, no embed call and no SQL issued against the search tables.

### D3 — Hit shape (`SearchHit`, a frozen value)

| Field | memo | session | entry |
|---|---|---|---|
| kind | `"memo"` | `"session"` | `"entry"` |
| id | the memo id | the session id | the message id |
| score | fused score (D1) | same | same |
| snippet | plain text, never None (D4) | **None** | plain text from FTS5 `snippet()` |
| memo level (`scope`, `scope_id`) | set | None | None |
| session_id | None | None | the entry's session id |

A memo hit has **no title, ever** (US-119). What a session result carries beyond its id is
`027`'s question; 025 gives it no text because `sessions` has no text column.

### D4 — Memo snippets: same shape from either arm

- Found by the lexical arm (alone or with the vector arm): the FTS5 `snippet()` text
  (`002.context.md`).
- Found by the vector arm only: the **leading extract** of `body`: collapse every
  whitespace run (spaces, tabs, newlines) to one space and strip both ends; if the result
  is longer than `SNIPPET_CHARS` characters, keep the first `SNIPPET_CHARS` characters and
  append `…` (U+2026, one character); otherwise use it as is.

Both are plain strings with no highlight markup.

### D5 — Filters first

Each arm ranks **only** within the candidate set: a select of base-relation ids carrying
the owner predicate and the extra predicate (`002`). Filtering after ranking is forbidden
(`search-and-retrieval.md` "Query shape"). The vector arm uses only the exact-scan form
(`003.context.md`); the vec0 KNN with a pushed-down id constraint (024 D3) must not appear.

### D6 — Owner scope in every query (R5)

Every SQL statement the port issues against a base relation — candidates and hit
hydration — carries `user_id = :user_id` in its own predicate. Isolation is tested as an
**absence**: another user's row that would match both arms never appears.

### D7 — Read posture

`search` only reads. It follows the read-transaction posture of the existing list
services (`services/memos.py` `_reading`, ~L216: the autobegun transaction is rolled back
after the reads). The pattern is replicated locally, never imported (it is private). The
embed call happens inside that read window; 025 holds no write lock.

## Cross-cutting constraints every step holds

- Sync SQLAlchemy **Core**; functions take `connection` first; the `search` package imports
  no `fastapi`.
- Backend fully typed; `mypy app` and `ruff check .` green after every step (commands in
  the root `CLAUDE.md`).
- Virtual tables are named only through 024's constants, never re-typed as string literals
  in 025 modules.

## Test conventions

From `backend/`. pytest, flat `tests/`, names `test_<behavior>__S025_<SSS>_DoD<n>`.

- DB via the existing `db_settings` / `db_engine` fixtures; each test runs
  `schema.metadata.create_all`, then creates the search tables with 024's
  `ensure_fts_tables` / `ensure_vector_tables` (when the test needs them present) and
  writes vectors with 024's `write_vector`. Rows are raw-inserted with file-local helpers,
  using **snowflake-sized ids (above 2^60)** and **two users** for isolation.
- A designated model is raw `llm_servers` + `models` rows with `is_enabled`,
  `is_embedding_designated` and `embedding_dim` (small, e.g. 8) — as 024's tests do.
- Vectors come from `llm_fakes.py`'s pure `(text, dim)` function; the fake factory is passed
  as `client_factory=`. **No monkeypatching.**
- Expected values come from this plan (D1–D4, the step contexts) and from the fake's pure
  vector function — never from calling the code under test.

## Vocabulary

| Term | Means here |
|---|---|
| **corpus / scope variant** | one of memo, session, entry (U1) |
| **base relation** | the table or view a variant's candidates come from |
| **candidate set** | ids of the base relation passing owner + extra predicate (D5) |
| **arm** | the vector ranking or the lexical ranking over the candidate set |
| **ranking** | an ordered list of distinct ids, best first, at most `ARM_DEPTH` long |
| **fused score** | D1's RRF sum |
| **leading extract** | D4's body-prefix snippet |
| **record row** | a `messages` row in `settled_entries` (024 vocabulary) |
