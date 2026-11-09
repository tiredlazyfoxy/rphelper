# fast/006.unicode-name-matching — context

Brief: `brief.md` (this folder). Its Definition and Scope are the boundary and are
not restated here.
Delivers: FEAT-017, US-147, UC-058. Repairs defect D-05 (`docs/plans/defects.md`).
Design: `docs/architecture/search-and-retrieval.md` ("My-search — FEAT-017",
"Three port variants and two `LIKE` corpora", the Defect D-05 paragraph) and
`docs/architecture/backend-structure.md` (database access: engine, connect
listener, PRAGMAs).
Superseded decision: `docs/plans/029.my-search/context.md` D3, third bullet only
("Case-insensitivity is SQLite `LIKE`'s: ASCII letters only"). D3's other bullets
(strip, one substring, escaping, either-column-matches-once) stand unchanged.

## What exists today (harvested)

- **The four `LIKE` sites.** `backend/app/services/search/my_search.py` has
  `search_characters` and `search_setups`. Each strips the query, returns `[]`
  without SQL on a blank needle, and matches inside an `or_` with
  `column.contains(needle, autoescape=True)`:
  - `characters.name` and `characters.sheet` (around lines 141-142);
  - `setups.name` and `setups.description` (around lines 194-195).

  Both are owner-scoped, ordered by `name` then `id`, and limited by
  `MY_SEARCH_PER_KIND_LIMIT`. There is no shared predicate helper. A comment
  (around line 132) and the docstrings (around lines 113-120) state the
  ASCII-only limitation. They become wrong with this change.
- **The engine.** `backend/app/db/engine.py` has exactly one `create_engine`,
  inside `get_engine(settings)`, cached per database path. It has one
  `connect` listener, `_on_connect(dbapi_connection, record)`, which runs in
  this order:
  1. `load_sqlite_vec(dbapi_connection)`, a module-level patchable seam whose
     failures are wrapped as `ExtensionLoadError`;
  2. `PRAGMA foreign_keys = ON`;
  3. `PRAGMA journal_mode = WAL`.

  Its docstring documents that order. A separate `begin` listener emits `BEGIN`.
- **No other connection source.** `app/` has no other `create_engine` and no
  `sqlite3.connect`. The Alembic batch executor, the whole-database replace and
  every test (`tests/conftest.py` `db_engine`) all get connections through
  `get_engine`. So a function registered in that listener exists on every
  connection the application and the suite ever use.
- **Nothing to collide with.** The backend has no `create_function`, no
  collation and no `casefold` anywhere today.
- **Existing tests.**
  - `backend/tests/test_db_engine.py` asserts only observable behaviour: FK on,
    WAL, `vec_version()`, and a failing loader raising `ExtensionLoadError`. An
    added registration breaks nothing there.
  - `backend/tests/test_my_search_like.py` covers the wildcard and escape cases
    (parametrized, backslash included), whitespace stripping, one-substring
    matching, ordering and owner scope, all with ASCII fixtures.
  - `backend/tests/test_my_search_service.py` covers the composed service.
  - The suite has no non-ASCII fixture anywhere.
- **No index to lose.** Neither table indexes a matched column, so wrapping the
  column in a function costs no index.

## Decisions (orchestrator-settled, binding)

1. **Mechanism: a registered SQLite scalar function, not a stored column and not
   a collation.** The engine's `connect` listener registers a one-argument
   function named `rp_casefold` on the raw DBAPI connection, with
   `deterministic=True`. It returns:
   - SQL NULL for a NULL input;
   - Python `str.casefold()` of a text input;
   - any other value (integer, blob) **unchanged**, so the function can never
     raise inside SQLite.

   Planner's placement call: register it **immediately after the `sqlite-vec`
   load and before the two PRAGMAs**, so capability registration happens
   together and the PRAGMAs stay last. The listener's docstring is updated to
   state the new order. The function name and the Python fold callable are
   module-level names in `app/db/engine.py`. The search code imports the name,
   so the string `"rp_casefold"` is spelled once.
2. **Predicate: fold both sides and keep SQLAlchemy's autoescape.** Each of the
   four sites becomes "the SQL fold of the column `contains` the Python
   casefold of the needle, with `autoescape=True`". The two folds are the same
   function, `str.casefold`, on both sides of the comparison.

   SQLAlchemy still escapes `%`, `_` and its own escape character (`/`) in the
   bound value and still emits the `ESCAPE` clause, so 029 D3's guarantee
   survives unchanged. `casefold` maps none of those three characters to
   anything else.

   One small private helper in `my_search.py` builds this predicate, and all four
   sites use it. Nothing changes in schema, columns or collation.
3. **Case folding only.** The change applies no accent or diacritic stripping and
   no Unicode normalization (NFC/NFD), per the brief's Out list. Consequences:
   - `É` matches `é`, because that is a case pair;
   - `é` does **not** match `e`;
   - a precomposed and a decomposed spelling of the same letter do not match
     each other.

   `ß` → `ss` (so `STRASSE` finds `Straße`) is an accepted consequence of
   `casefold` rather than `lower`, and is wanted: it is the Unicode-defined
   caseless match.
4. **Tests go in one new file.** `backend/tests/test_my_search_unicode.py` covers
   both the function's presence on engine connections and the four-column
   Unicode behaviour. The existing test files are not edited, and they must
   still pass.

## Constraints a coder must hold

- **R5.** Every statement keeps `user_id = :user_id`. The helper changes only
  the match term, never the `WHERE` skeleton.
- Ordering stays `name, id` over the raw stored `name` with SQLite's default
  binary collation, and is not folded. The limit, the blank-needle short-circuit
  and the strip are unchanged.
- `mypy app` and `ruff check .` are gates. `sqlite3.Connection.create_function`
  is typed in typeshed, and the fold callable needs an annotation that accepts
  any SQLite value.
- `ExtensionLoadError` wrapping stays scoped to the `sqlite-vec` load. The
  registration is not wrapped in it.
