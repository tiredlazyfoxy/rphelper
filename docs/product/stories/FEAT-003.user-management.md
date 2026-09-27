<!-- product-spec:start -->
# FEAT-003 — User management — stories

### US-008 — Admin creates an account
- **Actor:** ACT-001 · **Feature:** FEAT-003 · **Exercises:** UC-006
- **Story:** As an administrator, I want to create a new account, so that another person can use the instance.
- **Acceptance criteria:**
  - **US-008.AC-1** — Given the administrator is authenticated, when they supply credentials for a new account, then the instance creates the account, enabled.
  - **US-008.AC-2** — Given the account was created, when the administrator opens the account list, then the new account appears in it.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 7.

### US-009 — Disabling ends that user's sessions
- **Actor:** ACT-001 · **Feature:** FEAT-003 · **Exercises:** UC-007
- **Story:** As an administrator, I want disabling an account to end that user's active sessions immediately, so that access is cut off at once, not on their next login attempt.
- **Acceptance criteria:**
  - **US-009.AC-1** — Given a user holds an active session, when the administrator disables their account, then the instance ends that user's active sessions immediately.
  - **US-009.AC-2** — Given the account is disabled, when the user tries to log in again, then login is rejected.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 7.

### US-010 — Admin resets a password
- **Actor:** ACT-001 · **Feature:** FEAT-003 · **Exercises:** UC-008
- **Story:** As an administrator, I want to reset a user's password, so that they can regain access without me knowing their old one.
- **Acceptance criteria:**
  - **US-010.AC-1** — Given an account exists, when the administrator sets a new password for it, then the old password no longer works.
  - **US-010.AC-2** — Given the new password was set, when the user logs in with it, then login succeeds.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### US-011 — The account list shows no RP content
- **Actor:** ACT-001 · **Feature:** FEAT-003 · **Exercises:** UC-009
- **Story:** As an administrator, I want the account list to show accounts only, so that managing users never exposes their roleplay content.
- **Acceptance criteria:**
  - **US-011.AC-1** — Given the administrator opens the account list, when it is shown, then each account's identity and enabled/disabled status is shown.
  - **US-011.AC-2** — Given the account list is shown, when the administrator views it, then no character, session, setup or memo belonging to any account is shown.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 7.
<!-- product-spec:end -->
