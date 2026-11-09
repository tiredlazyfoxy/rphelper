# Fast feature 006 — unicode-name-matching

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-10-07 |

## Files Changed

- `backend/app/db/engine.py` — `casefold_sqlite_value` body; `rp_casefold` registered in `_on_connect` after the vec load, before the PRAGMAs; docstrings state the new order
- `backend/app/services/search/my_search.py` — `_folded_contains` body (`rp_casefold(column) LIKE` casefolded needle, autoescaped) used at the four match sites; ASCII-only wording replaced

## Skeleton

### Frozen interface (2026-10-07)
- `backend/app/db/engine.py` — `SqliteValue = str | bytes | int | float | None` (module-level type alias; return type is assignable to typeshed's `_SqliteData` for `create_function`) — new
- `backend/app/db/engine.py` — `CASEFOLD_FUNCTION_NAME: Final[str] = "rp_casefold"` — new
- `backend/app/db/engine.py` — `def casefold_sqlite_value(value: SqliteValue) -> SqliteValue` — new (stub raises `NotImplementedError`)
- `backend/app/db/engine.py` — `_on_connect(dbapi_connection: sqlite3.Connection, connection_record: Any) -> None` inside `get_engine` — unchanged signature; registration NOT wired by the skeleton (a throwing stub in the connect path would break every DB test). Coder adds `dbapi_connection.create_function(CASEFOLD_FUNCTION_NAME, 1, casefold_sqlite_value, deterministic=True)` after the vec load, before the PRAGMAs, outside the `ExtensionLoadError` wrapping, and updates the docstring order.
- `backend/app/services/search/my_search.py` — `def _folded_contains(column: ColumnElement[str], needle: str) -> ColumnElement[bool]` — new private helper (stub raises `NotImplementedError`); `ColumnElement` added to the `sqlalchemy` import. Not yet used at the four sites — coder swaps `characters.c.name`/`sheet` and `setups.c.name`/`description` `.contains(needle, autoescape=True)` for it, imports `CASEFOLD_FUNCTION_NAME` from `app.db.engine`, and updates the D3 comment/docstrings.
- `search_characters` / `search_setups` — signatures unchanged.
- Caller-compile edits (out of Source-files scope): None.

## Tests

### Tests (2026-10-07)
- `backend/tests/test_my_search_unicode.py` — covers DoD-1, DoD-2, DoD-3, DoD-4 — `rp_casefold` on `get_engine` connections (Cyrillic/Greek fold, NULL -> NULL, integer unchanged, present on two simultaneously held connections); `CASEFOLD_FUNCTION_NAME == "rp_casefold"`; `casefold_sqlite_value` on None/`Straße`/`ДОМ`/non-text
- `backend/tests/test_my_search_unicode.py` — covers DoD-5..DoD-11 — Cyrillic name in any case, sheet-only Cyrillic match, Greek setup name, description-only Cyrillic setup match, name+column double match appears once, `ß`<->`ss` both ways, `É`/`é` case-folded but `e` not matched
- `backend/tests/test_my_search_unicode.py` — covers DoD-12, DoD-13 — `%`, `_`, backslash and `/` mixed with Cyrillic match only the row holding the literal character (decoys `Дом`, `Дм`), characters and setups
- `backend/tests/test_my_search_unicode.py` — covers DoD-14, DoD-15, DoD-16 — owner scope with Cyrillic twins across needle cases; ASCII `Kaelith` by `KAELITH`/`kaeLITH`; binary `name, id` order over `АННА`/`Анна`x2/`анна`; blank needle returns `[]`
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓ (new ASCII test; existing three files untouched, verifier runs full suite), DoD-16 ✓, DoD-17 [verifier gate: mypy/ruff, no test], DoD-18 [manual/live, no test]

## Notes & Issues

_populated by the coder when worth saying_
