# Decisions — fast-006.unicode-name-matching
**Stage:** 006.repair · **Feature:** fast/006.unicode-name-matching

Case-insensitive name matching in any script for my-search (closes defect D-05).
The contracts are `search-and-retrieval.md` "Three port variants and three
`LIKE` matches" and `backend-structure.md` "Database access" (the connect
listener). Written at finalization (2026-11-09). `DEC-F006-5` corrects an
architect-session entry written after this feature shipped.

### DEC-F006-1 — A registered SQLite function, not a stored folded column and not a collation
- **Status:** accepted
- **Stage:** 006.repair · **Feature:** fast/006.unicode-name-matching · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** SQLite's `LIKE` folds case for ASCII only. What mechanism makes name matching case-insensitive in every script?
- **Decision:** A deterministic one-argument scalar function, `rp_casefold`, registered on every engine connection (`create_function(..., deterministic=True)`). It returns SQL NULL for NULL, Python `str.casefold()` for text, and any other value (integer, blob) unchanged, so it can never raise inside SQLite. The function name and the fold callable are module-level names in `app/db/engine.py`; the search code imports the name, so the string `"rp_casefold"` is spelled once.
- **Reason:** No matched column has an index that wrapping it in a function would lose, and a stored folded column would need a schema change plus a backfill. `app/` has no connection source other than `get_engine`, so the function exists on every connection the application and the suite use.
- **Rejected:** A stored folded (or normalized) column — schema change, backfill and a second value to keep in sync. A custom collation — `LIKE` does not consult collations.
- **Lands in:** `backend/app/db/engine.py`
- **Cites:** `backend-structure.md` § Database access; `search-and-retrieval.md` § Three port variants and three `LIKE` matches (flip condition: large-sheet latency, or an accent-insensitive requirement → a stored folded/normalized column, which is a schema change)

### DEC-F006-2 — Registration sits between the sqlite-vec load and the PRAGMAs
- **Status:** accepted
- **Stage:** 006.repair · **Feature:** fast/006.unicode-name-matching · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Where in the one `connect` listener is the function registered?
- **Decision:** Immediately after `load_sqlite_vec` and before `PRAGMA foreign_keys = ON` and `PRAGMA journal_mode = WAL`. The listener's docstring states the order. The registration is **not** wrapped in `ExtensionLoadError`, which stays scoped to the sqlite-vec load.
- **Reason:** Capability registration happens together and the PRAGMAs stay last. A registration failure is not an extension-load failure and must not be reported as one.
- **Lands in:** `backend/app/db/engine.py`
- **Cites:** `backend-structure.md` § Database access

### DEC-F006-3 — Fold both sides and keep SQLAlchemy's autoescape, through one helper
- **Status:** accepted
- **Stage:** 006.repair · **Feature:** fast/006.unicode-name-matching · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** How is each match predicate written so the escape guarantee survives?
- **Decision:** Every name-arm match is "`rp_casefold(column)` `contains` the Python `casefold()` of the needle, with `autoescape=True`", built by one private helper in `my_search.py`, `_folded_contains`. SQLAlchemy still escapes `%`, `_` and its escape character `/` in the bound value and still emits the `ESCAPE` clause; `casefold` maps none of those three characters to anything else. As delivered the helper served the four character and setup columns; the session-name arm added later by `034.session-names` uses the same helper (`DEC-F006-5`). The `WHERE` skeleton, the owner predicate, the strip, the blank-needle short-circuit and the limit are unchanged.
- **Reason:** One fold on both sides of the comparison, and one place the predicate is built, so no arm can drift to a different rule. User input still cannot act as a wildcard (029 D3).
- **Lands in:** `backend/app/services/search/my_search.py`
- **Cites:** `search-and-retrieval.md` § Three port variants and three `LIKE` matches

### DEC-F006-4 — Case folding only: no accent folding, no normalization
- **Status:** accepted
- **Stage:** 006.repair · **Feature:** fast/006.unicode-name-matching · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** How far does the fold go?
- **Decision:** Unicode case folding only. No accent or diacritic stripping and no NFC/NFD normalization: `É` matches `é`; `é` does not match `e`; a precomposed and a decomposed spelling of one letter do not match each other. `ß` matches `ss` (`STRASSE` finds `Straße`), an accepted and wanted consequence of `casefold` rather than `lower`. Ordering stays `name, id` over the raw stored `name` with SQLite's binary collation, not folded.
- **Reason:** The requirement is case-insensitivity; accent-insensitivity was out of the brief's scope. `casefold` is the Unicode-defined caseless match.
- **Supersedes:** 029 D3, third bullet only ("case-insensitivity is SQLite `LIKE`'s: ASCII letters only"), a plan-local decision with no DEC id. D3's other bullets (strip, one substring, escaping, either-column-matches-once) stand.
- **Lands in:** `backend/app/db/engine.py`; `backend/app/services/search/my_search.py`
- **Cites:** `search-and-retrieval.md` § Three port variants and three `LIKE` matches

### DEC-F006-5 — The session-name arm uses the same fold; correction of `DEC-arch-session-names-5`
- **Status:** accepted
- **Stage:** 006.repair · **Feature:** fast/006.unicode-name-matching · **Step:** —
- **Date:** 2026-11-09 · **Decided by:** user (finalization triage, from the code check)
- **Question:** `DEC-arch-session-names-5` (2026-11-05) and the matching architecture text said the session-name arm "inherits" D-05's ASCII-only caveat and that "any fix to D-05 must cover all three matches". fast/006 had already shipped on 2026-10-07. Which is true?
- **Decision:** The code is the truth: all three name arms — characters, setups and session names — match through `_folded_contains`, i.e. `rp_casefold` on both sides with autoescape. A non-Latin session name matches in any case. D-05 is closed for all three arms, and no further fix is owed.
- **Reason:** The 2026-11-05 architect session described the pre-fast/006 `LIKE`; feature 034 built the session-name arm on the then-current helper. Recorded as a correcting entry because decision ids are never edited away.
- **Supersedes:** `DEC-arch-session-names-5` **in part** — only its claim, in **Cites**, that D-05's ASCII-only caveat covers session names. The rest of that entry (a `LIKE` name arm, merged ahead of vector hits, the accepted unnamed-by-date limitation) stands.
- **Lands in:** `backend/app/services/search/my_search.py` (unchanged by this entry; its module docstring and two comments still say plain `LIKE` — an open code-comment cleanup, not a behaviour change)
- **Cites:** `search-and-retrieval.md` § Three port variants and three `LIKE` matches, § Decision history (2026-11-09)
