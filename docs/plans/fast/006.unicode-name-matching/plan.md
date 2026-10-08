# fast/006.unicode-name-matching — plan

Read `context.md` first. Its Decisions 1–4 are binding.

## Goal

Make my-search's character and setup matching case-insensitive in every script,
across all four `LIKE` columns. The change folds both sides of the comparison
through a deterministic SQLite function, `rp_casefold`, registered on every
engine connection. 029 D3's escape guarantee is preserved, and ordering, owner
scope and the limit are unchanged.

## Source files

- `backend/app/db/engine.py`: registers `rp_casefold` in the existing `connect`
  listener. Exposes the function name and the Python fold callable.
- `backend/app/services/search/my_search.py`: adds one shared folded-substring
  predicate helper, used at the four match sites. Updates the D3 comment and
  docstrings.

## Test files

- `backend/tests/test_my_search_unicode.py` (new): covers the function on engine
  connections and the Unicode behaviour of `search_characters` /
  `search_setups`.

Not edited, but each must still pass: `backend/tests/test_db_engine.py`,
`backend/tests/test_my_search_like.py`, `backend/tests/test_my_search_service.py`.

## Interface intent

- **Casefold function name constant** (`app/db/engine.py`, module level). This
  is the SQL name the function is registered under, `rp_casefold`. The search
  code references it rather than repeating the literal.
- **Python fold callable** (`app/db/engine.py`, module level, public). It takes
  one SQLite value and returns:
  - `None` for `None`;
  - `value.casefold()` for a `str`;
  - any other value unchanged.

  It never raises. It is the exact callable registered with SQLite, and tests
  may call it directly.
- **`connect` listener** (`_on_connect`, existing). After the `sqlite-vec` load
  and before the two PRAGMAs, it registers the fold callable on the raw DBAPI
  connection, under the constant name, with one argument and
  `deterministic=True`. The docstring states the new order: vec load,
  casefold registration, `foreign_keys`, WAL. Its signature is unchanged.
- **Folded-substring predicate helper** (`my_search.py`, private). It takes a
  column expression and the already-stripped needle, and returns a boolean SQL
  expression. That expression is true when the SQL fold of the column contains
  the Python casefold of the needle, as a literal substring. It keeps
  SQLAlchemy's `contains(..., autoescape=True)` semantics, so `%`, `_` and the
  escape character in the needle are escaped and the `ESCAPE` clause is
  emitted. All four sites use it: `characters.name`, `characters.sheet`,
  `setups.name` and `setups.description`.
- **`search_characters` / `search_setups`** (existing). Their signatures,
  return types, blank-needle short-circuit, owner predicate, `name, id` order
  and limit are unchanged. Only the match term changes, and the docstrings now
  say "case-insensitive in any script (Unicode case folding; no accent folding)"
  in place of the ASCII-only note.

## Definition of done

Function on the engine:

- **DoD-1 [test]**: On a connection obtained through `get_engine`, the SQL
  `SELECT rp_casefold('ДОМ')` returns `'дом'`, and `SELECT rp_casefold('ΣΟΦΙΑ')`
  returns `'σοφια'`.
- **DoD-2 [test]**: `SELECT rp_casefold(NULL)` returns NULL on such a connection,
  and an integer argument comes back unchanged with no error.
- **DoD-3 [test]**: The function is present on **every** pooled connection, not
  only the first. Two distinct connections checked out of the same engine at the
  same time both answer DoD-1's query.
- **DoD-4 [test]**: The module-level Python fold callable maps `None` to `None`,
  `'Straße'` to `'strasse'` and `'ДОМ'` to `'дом'`. The constant equals
  `'rp_casefold'`.

Unicode matching (each case through `search_characters` / `search_setups` on a
real engine):

- **DoD-5 [test]**: A character whose `name` is Cyrillic in mixed case (for
  example `Дмитрий`) is found by the needle typed all upper case, all lower case,
  and in a different mixed case.
- **DoD-6 [test]**: A character found **only** through its `sheet` (the name does
  not contain the needle) is found by a Cyrillic needle in a case different from
  the sheet's text.
- **DoD-7 [test]**: A setup is found through its `name` by a Greek needle in a
  different case.
- **DoD-8 [test]**: A setup found **only** through its `description` is found by a
  Cyrillic needle in a different case.
- **DoD-9 [test]**: A row whose `name` and `sheet` (or `name` and `description`)
  both match a case-different non-ASCII needle appears **exactly once**.
- **DoD-10 [test]**: `ß` folds both ways. A character named `Straße` is found by
  the needle `STRASSE`, and a character named `STRASSE` is found by the needle
  `straße`.
- **DoD-11 [test]**: Accents are **not** folded, but case is. A character named
  `Élodie` is found by the needle `élodie`, and **not** by `elodie`.

Escape guarantee with non-ASCII needles (029 D3 preserved):

- **DoD-12 [test]**: A needle mixing Cyrillic with `%`, for example `д%м`, does
  **not** match a row named `Дом` with no literal `%`. It **does** match a row
  whose name contains the literal `Д%М`.
- **DoD-13 [test]**: The same holds for `_` (for example `д_м` against `Дом` and
  `Д_М`), for a backslash and for the escape character `/` mixed with Cyrillic.
  Each matches only a row containing that literal character, in any case.

Unchanged behaviour:

- **DoD-14 [test]**: Owner scope holds. Another user's character and setup with
  Cyrillic names are never returned to the caller, whatever the case of the
  needle.
- **DoD-15 [test]**: ASCII case-insensitivity is unchanged. A character named
  `Kaelith` is found by `KAELITH` and by `kaeLITH`. The existing
  `test_my_search_like.py`, `test_my_search_service.py` and `test_db_engine.py`
  pass unmodified (verifier runs the full suite).
- **DoD-16 [test]**: Results are still ordered by stored `name`, then `id`, when
  several non-ASCII names match one needle. A blank or whitespace-only needle
  still returns an empty list.
- **DoD-17 [test]**: `mypy app` and `ruff check .` from `backend/` are clean
  (verifier gate).

Review:

- **DoD-18 [manual/live]**: Verifier inspection. Neither the comment nor the
  docstrings in `my_search.py` still describe matching as ASCII-only. They say
  the match is case-insensitive in any script with no accent folding. The
  `_on_connect` docstring lists the registration in its order.
  `app/db/schema.py` is untouched, and no collation is introduced anywhere.

## Out of scope

- The entry and memo arms (the `025` FTS/vector port), including FTS5 tokenizer
  case handling.
- Accent and diacritic folding, and Unicode normalization (NFC/NFD).
- A stored folded column, an index, a collation, or any `db/schema.py` /
  drift change.
- Result ordering (stays binary over the raw `name`), the archived flags, the
  per-kind limit, the blank-needle rule and the wire shape.
- Any frontend change.
- Using `rp_casefold` anywhere other than the four my-search sites.
- Editing `docs/plans/defects.md`, `docs/product/` or `docs/architecture/`.
