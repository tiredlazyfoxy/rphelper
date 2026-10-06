# fast/006.unicode-name-matching — Unicode name matching
<!-- roadmap:start -->
- **Stage:** 006.repair · **Track:** fast · **Size:** S
- **Delivers:** FEAT-017 (US-147, UC-058)
- **Depends on:** `029.my-search`

## Definition
A character or setup whose name is written in a non-Latin script is found whatever case the roleplayer types it in. Today the match is a SQLite `LIKE` substring and SQLite folds case for ASCII letters only, so a Cyrillic or Greek name matches only in the case typed. `docs/product/vision.md`'s premise is a roleplayer composing in a language they are not a confident writer in, which makes a non-Latin RP language the expected case rather than an edge one, so this is a real failure of UC-058 for the product's own core user.

## Scope
**In:**
- case-insensitive matching in any script for the four columns my-search matches with `LIKE` — `characters.name`, `characters.sheet`, `setups.name`, `setups.description`
- test coverage with non-ASCII fixtures, which the suite has none of today

**Out:**
- the entry and memo arms, which go through the `025` FTS/vector search and are unaffected
- accent and diacritic folding, and any normalization beyond case — matching a letter to its unaccented form is not asked for
- result ordering, the archived flags and the limit, all unchanged

## Open questions for the planner
- The predicate is `ColumnElement.contains(needle, autoescape=True)` at four call sites in two functions with no shared helper (`backend/app/services/search/my_search.py:141,142,194,195`), and SQLAlchemy owns the `ESCAPE` clause. `029` D3's escape handling must survive the fix — user input can never be allowed to act as a wildcard. Reproducing that correctly is the main risk here, not the folding itself.
- The backend registers no custom SQLite function and sets no collation anywhere. There is one engine and one `connect` listener (`backend/app/db/engine.py:143`), already carrying the `sqlite-vec` load as a patchable seam, and `backend/tests/test_db_engine.py` asserts on that listener's behaviour.
- A stored folded column instead would mean a `db/schema.py` change plus a backfill, which is past the fast track — if the harvest points that way, come back to `/roadmap` rather than stretching the pass. Neither table carries an index on any matched column today, so a per-row function costs no index that exists.
<!-- roadmap:end -->
