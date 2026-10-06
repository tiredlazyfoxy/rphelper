# Fast feature 005 — degraded-embedding-path

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-10-07 |

## Files Changed

- `backend/app/services/session_index.py` — degraded refresh catches `DEGRADED_EMBEDDING_ERRORS` and clears the session vector via owner-scoped `_clear_session_vector`; docstrings updated

## Skeleton

### Frozen interface (2026-10-07)
- `backend/app/services/session_index.py` — `DEGRADED_EMBEDDING_ERRORS: tuple[type[Exception], ...] = (NoEmbeddingModelError, LlmUnreachableError, SecretRefError)` — new (module-level constant with docstring; value is the declaration itself, complete; `SecretRefError` newly imported from `app.errors`)
- `backend/app/services/session_index.py` — `_clear_session_vector(connection: Connection, user_id: int, session_id: int) -> None` — new (private; stub body raises `NotImplementedError`)
- `backend/app/services/session_index.py` — `refresh_session_vector_degraded(connection: Connection, user_id: int, session_id: int, *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> bool` — signature unchanged; body and docstring deliberately left as-is (still catches only the old pair, no clear). The coder widens the except clause to `DEGRADED_EMBEDDING_ERRORS`, calls `_clear_session_vector` on a catch, and updates the docstring (also the module docstring's U5 paragraph, which says the stale row is kept)
- `backend/app/services/session_index.py` — `refresh_session_vectors(...)` — unchanged
- Caller-compile edits (out of Source-files scope): None.

## Tests

### Tests (2026-10-07)
- `backend/tests/test_session_index.py` — covers DoD-3, DoD-4, DoD-6, DoD-7, DoD-8, DoD-9, DoD-10, DoD-11, DoD-12, DoD-14 — the degraded wrapper: unset-credential degrades to `True`; each of the three causes (no model / unreachable / unset `$VAR`) clears a pre-existing vector and commits the relational write; no-row and no-table catches return `True`; owner scoping (A-calling-on-B leaves B byte-identical; A's catch leaves B byte-identical); `RuntimeError` factory propagates and rolls back; `DEGRADED_EMBEDDING_ERRORS` is exactly the three classes; strict path raises `SecretRefError` / `NoEmbeddingModelError` and keeps the vector; happy path returns `False` and writes. The four old 024 DoD-6 "keeps the stale vector" tests rewritten and renamed (`..._clears_the_vector__S024_003_DoD6__F005_DoD6`), including the dimension-mismatch case (cleared by session id in the 16-dim table).
- `backend/tests/test_record_keeping_embedding.py` — covers DoD-1, DoD-2, DoD-4, DoD-5, DoD-6, DoD-10, DoD-13 — settle and settled edit with an unset `$VAR` credential (service level and wire: 2xx, persisted, flag true, vector cleared); settled edit without a model clears the vector (service level and wire); `RuntimeError` factory on a settled edit propagates, old text and vector kept; memo create with unset credential answers 500 `secret_ref_missing` and stores nothing. Old-contract tests rewritten/renamed: `test_a_settle_without_a_model_clears_the_preexisting_vector__S024_005_DoD2__F005_DoD5`, `test_a_settle_with_an_unreachable_provider_has_the_same_outcome__S024_005_DoD2__F005_DoD6`, `test_a_settled_edit_without_a_model_saves_flags_and_clears_the_vector__S024_005_DoD5__F005_DoD5`; module docstring U5 line updated.
- Both files gain an autouse fixture deleting `F005_UNSET_EMBEDDING_KEY`, and `_seed_designation` gains an `api_key_ref=` keyword (default `None`, existing callers unchanged).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 [manual/live, no test]

## Notes & Issues

- `ruff check .` fails on E501 in `backend/tests/test_session_index.py:661` (test function name 121 chars, test-coder's file); `ruff check app` and `mypy app` are clean.
