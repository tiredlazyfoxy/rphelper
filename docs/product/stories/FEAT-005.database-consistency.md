<!-- product-spec:start -->
# FEAT-005 — Database consistency & management — stories

### US-017 — Drift report lists per-table status
- **Actor:** ACT-001 · **Feature:** FEAT-005 · **Exercises:** UC-014
- **Story:** As an administrator, I want a per-table drift report, so that I know the database's structural health at a glance.
- **Acceptance criteria:**
  - **US-017.AC-1** — Given the administrator opens the drift report, when it loads, then it lists each table's status — in sync, missing, or drifted.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### US-018 — Remediation creates missing tables
- **Actor:** ACT-001 · **Feature:** FEAT-005 · **Exercises:** UC-015
- **Story:** As an administrator, I want to remediate reported drift, so that the database structure is brought back into sync.
- **Acceptance criteria:**
  - **US-018.AC-1** — Given the drift report shows a missing or drifted table, when the administrator requests remediation, then the instance creates missing tables and brings drifted structures into sync.
  - **US-018.AC-2** — Given remediation completed, when the administrator views the drift report again, then it reflects the corrected state.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### US-019 — Vector index rebuild
- **Actor:** ACT-001 · **Feature:** FEAT-005 · **Exercises:** UC-016
- **Story:** As an administrator, I want to rebuild the vector index, so that the assistant's semantic tools work against current data.
- **Acceptance criteria:**
  - **US-019.AC-1** — Given the administrator requests a vector-index rebuild, when it completes, then the instance reports completion.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.
<!-- product-spec:end -->
