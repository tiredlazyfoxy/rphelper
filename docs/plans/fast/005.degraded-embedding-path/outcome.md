# fast/005.degraded-embedding-path — outcome

Intended doc changes, for the architect to apply at finalization.

## docs/architecture/search-and-retrieval.md

- **Section:** "Failure mode, and a deliberate asymmetry between two write paths"
  (the caught-set paragraph)
  **Change:**
  - The caught set is now three errors:
    - `no_embedding_model`, including `dimension_mismatch`;
    - `llm_unreachable`;
    - `secret_ref_missing`.
  - It is defined once as a named tuple in `services/session_index.py`.
  - It is a **named set, not a base type**, on purpose: any other exception
    (programming, SQL) still propagates and rolls the write back. A bug never
    turns into "coverage incomplete".
  - The strict path still catches none of them. Their statuses stay 409, 502
    and 500.
  **Reason:** US-112.AC-1, widened to "credentials cannot be used". D-03 fixed.

- **Section:** same section, "Consequences to hold"
  **Change:**
  - A degraded write **clears** the session's `session_vec` row; it no longer
    leaves the row stale.
  - So after a degraded write a session has **no** vector rather than a stale
    one. It is absent from semantic search until UC-016's rebuild.
  - "No staleness marker and no staleness column" (024 U5, first half) still
    stands.
  - Replace "a missing or stale `session_vec` row" with "a missing
    `session_vec` row". A stale row is now only possible from a superseded
    designation (the UC-013 sharp edge), not from the degraded path.
  **Reason:** US-112.AC-3. This is the accepted consequence in `features.md`
  (finalization 2026-10-06).

- **Section:** "Two defects live on the degraded path"
  **Change:** Remove the subsection, or convert it to an as-built note that
  D-03 and D-04 are fixed by `fast/005`. The clear resolves its id through an
  owner-scoped `select` on `sessions.id` before calling `delete_vector`, as the
  derived-store rule requires.
  **Reason:** Both defects are closed.

- **Section:** "The invalidation fan-out…" (the flip-condition paragraph:
  "the degraded-write path already tolerates a stale `session_vec` row")
  **Change:** Reword it to say that the path tolerates a **missing**
  `session_vec` row.
  **Reason:** The degraded path no longer produces stale rows.

- **Section:** "Index rebuild — FEAT-005" ("every session whose `session_vec`
  went stale while no embedding model was designated")
  **Change:** Reword to "every session whose `session_vec` was cleared by a
  degraded write".
  **Reason:** As above.

## docs/architecture/session-stream.md

- **Section:** the degraded embedding path
  **Change:** Mirror the three-error caught set and the clear-on-catch behaviour
  stated above, if the section restates them.
  **Reason:** Keep the backend counterpart consistent.

## docs/architecture/backend-structure.md

- **Section:** the error model / strict-vs-degraded table ("carries the same
  table")
  **Change:** Add `secret_ref_missing` to the degraded path's caught set. Note
  that the clear happens on catch.
  **Reason:** This doc carries the same table as `search-and-retrieval.md`.

## docs/architecture/quick-reference.md

- **Section:** the defects block
  **Change:** Mark D-03 and D-04 as fixed by `fast/005.degraded-embedding-path`,
  or remove them.
  **Reason:** Closed.

## docs/plans/defects.md (owner to apply; not an architecture doc)

- **Entries:** D-03 and D-04
  **Change:** Mark both as resolved by `fast/005.degraded-embedding-path`.
  **Reason:** Closed.

## Observations
