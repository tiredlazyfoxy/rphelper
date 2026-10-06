# fast/005.degraded-embedding-path — plan

## Goal

The degraded `session_vec` refresh catches every embedding-side failure. That
set now includes an unusable credential (`secret_ref_missing`), so settle,
re-open, partner filing and settled edits always commit and report
`search_coverage_incomplete: true` when embedding fails. On every degraded catch
it also clears the session's existing vector, through an owner-scoped id
lookup. (FEAT-009; US-112.AC-1, US-112.AC-3.)

## Source files

- `backend/app/services/session_index.py`: this file gets the named
  caught-exception set and the owner-scoped clear helper. The changed body of
  `refresh_session_vector_degraded` also lives here.

## Test files

- `backend/tests/test_session_index.py`: unit tests for the degraded wrapper.
  Covers the caught set, clearing, owner scoping, propagation of other errors,
  and the strict function's strictness.
- `backend/tests/test_record_keeping_embedding.py`: router-level tests for
  settle and settled edits with an unusable credential, and for clearing. Also
  shows that the memo strict path still fails with an unset key.

## Interface intent

- **Degraded-error set** (new; a module-level constant in `session_index.py`,
  public name, for example `DEGRADED_EMBEDDING_ERRORS`). It is a tuple of
  exactly three exception classes: `NoEmbeddingModelError`,
  `LlmUnreachableError` and `SecretRefError`. A comment or docstring states
  three things:
  - the tuple is the complete boundary of what the degraded path swallows;
  - it is a named set on purpose, so that programming and SQL errors still
    propagate;
  - the strict path ignores it.
- **Owner-scoped vector clear** (new; private helper in `session_index.py`).
  - Input: the connection, the acting user's id and one session id.
  - It resolves the id through a `select` on `sessions.id` that is restricted
    to that id **and** that user.
  - It then calls `delete_vector` on `SESSION_VEC_TABLE` for each id the select
    returns.
  - It returns nothing. It is a no-op when the session is not the user's, when
    the row is absent, or when the table is absent.
- **`refresh_session_vector_degraded`** (changed behaviour; the signature does
  not change).
  - It still delegates to the strict `refresh_session_vectors` for the one
    session.
  - Its except clause now uses the degraded-error set.
  - On a catch it calls the owner-scoped clear for that user and session, then
    returns `True`.
  - On success it returns `False`, as today.
  - Any exception outside the set propagates unchanged.
  - Its docstring is updated so that it no longer says the stale vector is
    kept, and so that it no longer says `SecretRefError` propagates.
- **`refresh_session_vectors`** (strict): unchanged.

## Definition of done

- **DoD-1 [test]**: An unusable embedding credential no longer blocks a settled
  edit (US-112.AC-1). The designated embedding server's API key ref names an
  unset `$ENV_VAR`. A settled-entry text edit responds 2xx (not 500), the new
  text is persisted, and the response carries `search_coverage_incomplete: true`.
- **DoD-2 [test]**: An unusable embedding credential no longer blocks settle.
  The setup is the same as DoD-1. Settling responds 2xx, the settle is
  persisted, and the response carries `search_coverage_incomplete: true`.
  (US-112.AC-1)
- **DoD-3 [test]**: With an unusable credential, `refresh_session_vector_degraded`
  returns `True` and does not raise. (US-112.AC-1)
- **DoD-4 [test]**: A degraded catch clears the session's pre-existing vector
  (US-112.AC-3). The session has a `session_vec` row from an earlier successful
  embed. For each of the three causes the row is gone afterwards and the call
  returns `True`. The causes are: no designated embedding model,
  embedding server unreachable, and unset `$ENV_VAR` credential.
- **DoD-5 [test]**: Clearing is visible at the router level (US-112.AC-3). The
  session had a vector before a settled edit made with no designated embedding
  model. After the edit commits, the session has no `session_vec` row. This
  replaces the old "stale vector byte-identical" expectation at
  `test_record_keeping_embedding.py` ~583.
- **DoD-6 [test]**: The unit-level stale-vector test at `test_session_index.py`
  ~610 ("keeps the stale vector") is rewritten so that it expects the vector to
  be cleared. No test in either file asserts that a degraded catch keeps a
  pre-existing vector.
- **DoD-7 [test]**: A degraded catch with no pre-existing vector, including the
  case where the `session_vec` table does not exist, returns `True` and raises
  nothing.
- **DoD-8 [test]**: Owner scoping. User B's session has a `session_vec` row. A
  degraded refresh is called as user A with B's session id, while embedding is
  unavailable. B's row is still present and byte-identical afterwards, whatever
  the call returns.
- **DoD-9 [test]**: Owner scoping. Users A and B each have a session with a
  vector. A degraded catch for A's session clears A's row and leaves B's row
  byte-identical.
- **DoD-10 [test]**: The boundary is a named set. If the embedding side raises
  an exception outside the three named classes (for example, a fake client
  factory raising `RuntimeError`), `refresh_session_vector_degraded` propagates
  it and does not return `True`. At the router level, a settled edit under that
  fault does not commit: the old text remains and any pre-existing vector is
  untouched.
- **DoD-11 [test]**: The degraded-error set is exactly `NoEmbeddingModelError`,
  `LlmUnreachableError` and `SecretRefError`.
- **DoD-12 [test]**: The strict path is unchanged. With an unset `$ENV_VAR`
  credential and a non-empty session text, `refresh_session_vectors` raises
  `SecretRefError`. With no designated model it raises `NoEmbeddingModelError`.
  Neither call deletes any existing vector.
- **DoD-13 [test]**: The memo strict path still fails. With an unset `$ENV_VAR`
  credential, creating a memo with a non-empty body responds 500
  `secret_ref_missing`, and no memo row is stored.
- **DoD-14 [test]**: A successful degraded-wrapper call (embedding available)
  still returns `False` and writes the session's vector. This guards the happy
  path against regression.
- **DoD-15 [manual/live]**: `mypy app` and `ruff check .` pass from `backend/`.

## Out of scope

- Any change to `refresh_session_vectors` (strict), memo write paths, the
  persona and setup fan-outs, `index_rebuild.py`, or the search and query side.
- Recording that material is unembedded: no staleness column, no marker, no
  persisted coverage state (`024` U5, first half, stands).
- The whole-index rebuild (`fast/002`) that later restores cleared sessions to
  semantic search.
- Changing `SecretRefError`'s class, code or HTTP status, or introducing an
  embedding-specific exception base.
- Any change to the callers in `settle.py` / `messages.py`, routers, wire
  models or the frontend banner. `search_coverage_incomplete` already flows
  end-to-end.
- Clearing `memo_vec` or any FTS table. Memos have no degraded path, and FTS is
  trigger-maintained.
