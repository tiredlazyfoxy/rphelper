<!-- product-spec:start -->
# FEAT-001 — First-run bootstrap — use cases

### UC-001 — Create a new database with the first administrator
- **Actor:** ACT-003
- **Feature:** FEAT-001
- **Preconditions:** No database exists; instance is unconfigured.
- **Main flow:**
  1. Operator opens the unconfigured instance, arriving at the main address, the sign-in address or the administration address.
  2. Instance offers to create a new database.
  3. Operator chooses to create new and supplies the first administrator's credentials.
  4. Instance creates the database and the first administrator account.
  5. Operator is signed in as the administrator (becomes ACT-001).
- **Alternate flows:**
  - 1a. The browser still holds a sign-in from a previous database, and the instance still offers bootstrap — the operator is shown the bootstrap offer, not a sign-in form or an endless waiting state (US-148).
- **Postconditions:** Database holds exactly one administrator account; bootstrap is no longer offered (UC-003).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7; interview 2026-10-07.

### UC-002 — Bring up an instance from an existing export
- **Actor:** ACT-003
- **Feature:** FEAT-001
- **Preconditions:** No database exists; instance is unconfigured; operator holds a previously produced whole-database export (FEAT-018).
- **Main flow:**
  1. Operator opens the unconfigured instance, arriving at the main address, the sign-in address or the administration address.
  2. Instance offers to import an existing export.
  3. Operator supplies the export.
  4. Instance restores the database from the export, including every user and administrator it contained.
  5. Operator signs in as one of the restored administrators.
- **Alternate flows:**
  - 1a. The browser still holds a sign-in from a previous database, and the instance still offers bootstrap — the operator is shown the bootstrap offer, not a sign-in form or an endless waiting state (US-148).
- **Postconditions:** Database populated from the export; bootstrap is no longer offered (UC-003).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7, round 1, round 2; interview 2026-10-07.

### UC-003 — Bootstrap is unavailable once the instance is configured
- **Actor:** ACT-003
- **Feature:** FEAT-001
- **Preconditions:** Instance is already configured — a database and at least one administrator exist.
- **Main flow:**
  1. Someone reaches the bootstrap entry point.
  2. Instance detects it is already configured.
  3. Instance refuses to create a new database or import an export.
  4. Instance directs them to sign in instead.
- **Postconditions:** Existing database untouched; bootstrap stays unavailable for the life of the instance.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.
<!-- product-spec:end -->
