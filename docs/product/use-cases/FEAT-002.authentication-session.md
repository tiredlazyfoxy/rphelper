<!-- product-spec:start -->
# FEAT-002 — Authentication & session — use cases

### UC-004 — Log in
- **Actor:** ACT-001, ACT-002
- **Feature:** FEAT-002
- **Preconditions:** Account exists.
- **Main flow:**
  1. User supplies credentials at the login screen.
  2. Instance verifies credentials against the account.
  3. Credentials correct and account enabled — instance opens a session and shows the user's home.
- **Alternate flows:**
  - Credentials incorrect — login rejected, user remains at the login screen.
  - Account disabled — login rejected, user remains at the login screen.
- **Postconditions:** On success, an active session tied to the user; on any rejection, no session.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### UC-005 — Log out and session expiry
- **Actor:** ACT-001, ACT-002
- **Feature:** FEAT-002
- **Preconditions:** User holds an active session.
- **Main flow:**
  1. User chooses to log out.
  2. Instance ends the session.
  3. User is returned to the login screen.
- **Alternate flows:**
  - Session expires on its own — the user's next action returns them to the login screen instead.
- **Postconditions:** Session ended; user must log in again to resume.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.
<!-- product-spec:end -->
