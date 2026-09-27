<!-- product-spec:start -->
# FEAT-002 — Authentication & session — stories

### US-004 — Log in with correct credentials
- **Actor:** ACT-001, ACT-002 · **Feature:** FEAT-002 · **Exercises:** UC-004
- **Story:** As an administrator or roleplayer, I want to log in with my correct credentials, so that I can reach my account.
- **Acceptance criteria:**
  - **US-004.AC-1** — Given an account exists and is enabled, when the user supplies correct credentials, then the instance opens a session tied to that user.
  - **US-004.AC-2** — Given login succeeded, when the session opens, then the user's home is shown.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### US-005 — Rejected with wrong credentials
- **Actor:** ACT-001, ACT-002 · **Feature:** FEAT-002 · **Exercises:** UC-004
- **Story:** As an administrator or roleplayer, I want incorrect credentials to be rejected, so that only I can open my account.
- **Acceptance criteria:**
  - **US-005.AC-1** — Given an account exists, when the user supplies incorrect credentials, then login is rejected.
  - **US-005.AC-2** — Given login was rejected, when the rejection is shown, then the user remains at the login screen.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### US-006 — A disabled account cannot log in
- **Actor:** ACT-001, ACT-002 · **Feature:** FEAT-002 · **Exercises:** UC-004
- **Story:** As an administrator, I want a disabled account to be unable to log in, so that disabling an account is effective immediately.
- **Acceptance criteria:**
  - **US-006.AC-1** — Given an account is disabled, when its correct credentials are supplied, then login is rejected.
  - **US-006.AC-2** — Given an account is disabled and login was rejected, when the rejection is shown, then the user remains at the login screen.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 7.

### US-007 — Session ends, return to login
- **Actor:** ACT-001, ACT-002 · **Feature:** FEAT-002 · **Exercises:** UC-005
- **Story:** As an administrator or roleplayer, I want to log out or have my session expire, so that my account isn't left open indefinitely.
- **Acceptance criteria:**
  - **US-007.AC-1** — Given a user holds an active session, when they log out, then they are returned to the login screen.
  - **US-007.AC-2** — Given a user's session expires on its own, when they next act, then they are returned to the login screen.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.
<!-- product-spec:end -->
