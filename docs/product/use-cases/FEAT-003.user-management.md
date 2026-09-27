<!-- product-spec:start -->
# FEAT-003 — User management — use cases

### UC-006 — Create an account
- **Actor:** ACT-001
- **Feature:** FEAT-003
- **Preconditions:** Administrator is authenticated.
- **Main flow:**
  1. Administrator opens account creation.
  2. Administrator supplies the new account's credentials.
  3. Instance creates the account.
  4. New account appears in the account list, enabled.
- **Postconditions:** Account exists and can log in (FEAT-002).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 7.

### UC-007 — Disable and re-enable an account
- **Actor:** ACT-001
- **Feature:** FEAT-003
- **Preconditions:** Account exists.
- **Main flow:**
  1. Administrator selects an account.
  2. Administrator disables it.
  3. Instance ends that user's active sessions immediately.
  4. Disabled account can no longer log in (UC-004 alternate flow).
- **Alternate flows:**
  - Administrator re-enables a disabled account — account can log in again.
- **Postconditions:** Disabling ends the account's active sessions at once; re-enabling restores login ability.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 7.

### UC-008 — Reset a user's password
- **Actor:** ACT-001
- **Feature:** FEAT-003
- **Preconditions:** Account exists.
- **Main flow:**
  1. Administrator selects an account.
  2. Administrator sets a new password for it.
  3. Instance applies the new password.
- **Postconditions:** The old password no longer works; the user must use the new one to log in.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### UC-009 — List accounts without reaching any content
- **Actor:** ACT-001
- **Feature:** FEAT-003
- **Preconditions:** Administrator is authenticated.
- **Main flow:**
  1. Administrator opens the account list.
  2. Instance shows every account's identity and enabled/disabled status.
  3. Administrator sees no character, session, setup or memo belonging to any account.
- **Postconditions:** Account list shown; no RP content exposed (FEAT-019).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 7.
<!-- product-spec:end -->
