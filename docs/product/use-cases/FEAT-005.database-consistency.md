<!-- product-spec:start -->
# FEAT-005 — Database consistency & management — use cases

### UC-014 — View a per-table drift report
- **Actor:** ACT-001
- **Feature:** FEAT-005
- **Preconditions:** Administrator is authenticated.
- **Main flow:**
  1. Administrator opens the drift report.
  2. Instance lists each table's status.
- **Postconditions:** Administrator sees which tables are in sync, missing, or drifted.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### UC-015 — Remediate drift
- **Actor:** ACT-001
- **Feature:** FEAT-005
- **Preconditions:** Drift report shows an issue (UC-014).
- **Main flow:**
  1. Administrator reviews the drift report.
  2. Administrator requests remediation.
  3. Instance creates missing tables and brings drifted structures into sync.
  4. Drift report reflects the corrected state.
- **Postconditions:** Reported drift resolved.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### UC-016 — Rebuild the vector index
- **Actor:** ACT-001
- **Feature:** FEAT-005
- **Preconditions:** Administrator is authenticated.
- **Main flow:**
  1. Administrator requests a vector-index rebuild.
  2. Instance rebuilds it.
  3. Instance reports completion.
- **Postconditions:** Semantic tools (FEAT-014, FEAT-015) work against the rebuilt index.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.
<!-- product-spec:end -->
