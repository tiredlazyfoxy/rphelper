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
  - **US-010.AC-3** — Given the user holds an active session, when the administrator resets their password, then that session stays active.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7; finalization 2026-10-01, C35.

### US-011 — The account list shows no RP content
- **Actor:** ACT-001 · **Feature:** FEAT-003 · **Exercises:** UC-009
- **Story:** As an administrator, I want the account list to show accounts only, so that managing users never exposes their roleplay content.
- **Acceptance criteria:**
  - **US-011.AC-1** — Given the administrator opens the account list, when it is shown, then each account's identity and enabled/disabled status is shown.
  - **US-011.AC-2** — Given the account list is shown, when the administrator views it, then no character, session, setup or memo belonging to any account is shown.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 7.

### US-140 — Admin changes an account's role
- **Actor:** ACT-001 · **Feature:** FEAT-003 · **Exercises:** UC-087
- **Story:** As an administrator, I want to change an account's role, so that I can promote or demote a user without recreating their account.
- **Acceptance criteria:**
  - **US-140.AC-1** — Given an account that is not the acting administrator's own, when the administrator changes its role, then the account holds the new role.
  - **US-140.AC-2** — Given the administrator targets their own account, when they try to change its role, then the change is refused and the role is unchanged.
  - **US-140.AC-3** — Given a user holds an active session and their role is changed, when they next act, then they act with the new role, without logging in again.
- **Source:** `[confirmed: user]` finalization 2026-10-01, C31; shipped in docs/plans/005.admin-shell-and-users/.
<!-- product-spec:end -->
