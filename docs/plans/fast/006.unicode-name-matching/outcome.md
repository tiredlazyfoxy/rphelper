# fast/006.unicode-name-matching — outcome

Intended doc changes, for the architect to apply at finalization.

## docs/architecture/search-and-retrieval.md

- **Section:** "My-search — FEAT-017" → "Three port variants and two `LIKE`
  corpora", the "**Defect D-05**" paragraph
  **Change:** Replace the defect paragraph with the as-built decision:
  - Character and setup matching folds **both sides** through
    `rp_casefold`, a deterministic SQLite function registered on every engine
    connection. It is Python's `str.casefold`.
  - The needle is casefolded in Python, so the match is case-insensitive in any
    script. US-147 is satisfied.
  - SQLAlchemy's `contains(autoescape=True)` still escapes `%`, `_` and `/` and
    still emits `ESCAPE`, so user input still cannot act as a wildcard.
  - It is case folding only. It does no accent or diacritic folding and no
    Unicode normalization: `É` matches `é`, `é` does not match `e`, and `ß`
    matches `ss`.
  - Ordering remains binary over the raw `name`.

  Also state why: there was no index on any matched column to lose, and a stored
  folded column would have needed a schema change plus a backfill.

  **Flip condition:** if per-row folding becomes visible in latency on large
  sheets, or if accent-insensitive matching is ever required, the move is to a
  stored folded/normalized column. That is a schema change, not a predicate
  tweak.

  **Reason:** Closes D-05. Supersedes 029 D3's ASCII-only bullet.
- **Section:** same section, the sentence "The match is a plain **escaped,
  case-insensitive substring over one needle, not tokenised**"
  **Change:** Qualify "case-insensitive" as "case-insensitive in any script
  (Unicode case folding)".
  **Reason:** As-built record.

## docs/architecture/backend-structure.md

- **Section:** Database access (engine, connect listener, PRAGMAs)
  **Change:** Record that the one `connect` listener now does three things, in
  this order:
  1. loads `sqlite-vec`;
  2. registers the deterministic one-argument SQL function `rp_casefold`;
  3. sets the two PRAGMAs.

  `rp_casefold` maps NULL to NULL, text to `str.casefold()`, and any other value
  to itself unchanged. It never raises.

  Name the consequence: the function exists **only** on connections from
  `get_engine`. A statement using it fails on a raw `sqlite3` connection or in
  the sqlite3 CLI. That is acceptable because `app/` has no other connection
  source. It is not a schema object, so drift never sees it.

  **Reason:** The first custom SQL function in the backend. Records a capability
  the engine now guarantees.

## docs/architecture/quick-reference.md

- **Section:** Paths (`backend/app/db/engine.py` row)
  **Change:** Extend "one connect listener" to "one connect listener (sqlite-vec
  load + `rp_casefold` registration + PRAGMAs)".
  **Reason:** As-built record.
- **Section:** the defects block
  **Change:** Mark D-05 repaired by `fast/006.unicode-name-matching` (or remove
  it, per the block's convention).
  **Reason:** Defect closed.

## Flags for other owners

- `docs/product/features.md`: FEAT-017's `**Remaining:**` line should drop
  US-147 once this plan is `done`. This belongs to `/product-spec`.
- `docs/plans/defects.md` D-05 names `/bug-fixer` against `029` as its vehicle.
  The roadmap routed it to this fast plan instead. `defects.md` tracks no
  status, so no edit is required, but a reader following D-05 should find this
  plan.

## Observations
