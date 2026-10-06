# Feature 032 — privacy-isolation-audit — intended documentation changes

Planner section: what the architect applies at finalization. Grouped by
target file.

## `docs/architecture/deployment.md`

- **Section:** "loguru's `diagnose` / backtrace must be off for the file sink"
  — **Change:** broaden to **every** loguru sink (console/stderr and file):
  `diagnose=False`, `backtrace=False`. Retitle accordingly. — **Reason:** the
  console sink kept loguru's default `diagnose=True` and leaked traceback locals
  into console/supervisord output; fixed in step 001.
- **Section:** "The redaction rule" — **Change:** add that access-log lines
  record the path **without** its query string (a filter on the
  `uvicorn.access` logger), because query strings can carry user text
  (`GET /api/search?q=`, 029). — **Reason:** step 001's fix of the first leak
  found.
- **Section:** "The redaction rule" — **Change:** add that the engine is built
  with bound parameters hidden and that the `sqlalchemy` loggers stay at
  WARNING or above — defence in depth so SQL parameters never reach a log line
  or a rendered statement error. — **Reason:** step 001 / step 007 DoD-9.
- **Section:** "The redaction rule" — **Change:** point to the enforcement
  tests (`backend/tests/test_logging_redaction.py`,
  `backend/tests/test_privacy_audit_logs.py`: dynamic sentinel sweep at level
  0). — **Reason:** the rule is now proved, not only stated.
- **Section:** nginx / production topology — **Change:** record
  `_TBD: nginx's own access_log records full request URIs including query
  strings, so GET /api/search?q=<user text> lands in the nginx access log; the
  fix (a log_format without $args / $request_uri, or access_log off for /api/)
  belongs to the deployment surface (fast/001) and is not made by 032._` —
  **Reason:** found during 032 planning; out of 032's scope.

## `docs/architecture/domain-rules.md`

- **Section:** R5 — **Change:** add an "Enforcement test" pointer: the route
  enumeration in `docs/plans/032.privacy-isolation-audit/context.md` and the
  route-classification guard (`backend/tests/test_privacy_audit_routes.py`)
  that fails when any API route is unclassified; plus the admin-invariance
  test (admin responses identical before/after user content exists) as the
  proof that no count derived from user content exists. — **Reason:** R5 had no
  single enforcement point.
- **Section:** R5 — **Change:** state explicitly that an admin calling a
  user-content route is an ordinary owner (sees only their own content);
  admins are not super-readers. — **Reason:** asserted by step 003 DoD-3;
  previously implicit.

## `docs/architecture/backend-structure.md`

- **Section:** routers / error model — **Change:** add the rule that every new
  API route must be added to the classification table of the privacy guard
  (`public` / `self` / `registry` / `owner` / `admin`) or the build fails; and
  name "refusal identity" (foreign id ⇒ response identical to unknown id). —
  **Reason:** step 002's guard makes this a build-time contract.

## `docs/architecture/admin-surfaces.md`

- **Section:** access gate / pages — **Change:** record that the `admin`
  entry's own files call only `/api/admin/`, `/api/me`, `/api/auth/`,
  `/api/health` (Vitest-enforced), and that admin responses are invariant under
  user content (tested). — **Reason:** step 006.
- **Section:** Database page / vector rebuild — **Change:** record whether the
  fast/002 rebuild response carries any count (expected: none, per the 032
  brief) as resolved by step 006. — **Reason:** "not a count derived from any
  of it".

## `docs/architecture/data-model.md`

- **Section:** ownership columns — **Change:** observation:
  `messages.user_id` is not constrained to equal the parent
  `sessions.user_id`, and `memos.scope_id` has no FK; isolation rests on the
  owner predicate in every query. No API path writes an inconsistent row, so
  this is recorded, not changed. — **Reason:** surfaced by the harvest; the
  audit deliberately does not seed such rows.

## `docs/architecture/search-and-retrieval.md`

- **Section:** the three search surfaces / hybrid port — **Change:** point to
  `backend/tests/test_privacy_audit_search_tools.py` as the cross-user proof
  for my-search, the hybrid port, the three tools and the vector/FTS write
  paths (the `vec0`/FTS tables have no user column; scoping is via candidate
  ids). — **Reason:** step 004.

## Observations

- Step 004: `write_vector` / `delete_vector` take no user id, so in the derived
  stores the owner predicate must live in the *caller's* own SQL — the one leak
  this audit found (`refresh_session_vectors`' empty-text delete) was exactly
  that predicate missing. Possible impact: in
  `docs/architecture/search-and-retrieval.md`, state alongside "the `vec0`/FTS
  tables have no user column" that every write to them must resolve its row ids
  through an owner-scoped query first.

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B1 (the backend spine — `session-stream.md`, `transfer.md`, `backend-structure.md`, `data-model.md`, `domain-rules.md`) and B2 (the LLM/search/operations layer — `llm-and-streaming.md`, `search-and-retrieval.md`, `deployment.md`, `admin-surfaces.md`, `overview.md`).
Rejected items: none
Notes: Its step 004 `## Observation` applied — every write to a `vec0` or FTS table must resolve its row ids through an owner-scoped query first, which is the one leak the audit found. Its `fast/002` count item is recorded as a requirement on that unbuilt plan rather than as an as-built fact, the residual question of whether UC-016's completion report may carry an aggregate over all users' material is surfaced rather than decided, and its new nginx access-log `_TBD:` is recorded as open and owned by `fast/001`.
