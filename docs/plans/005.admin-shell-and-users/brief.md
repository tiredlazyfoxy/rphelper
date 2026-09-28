# 005.admin-shell-and-users — Admin shell and user management
<!-- roadmap:start -->
- **Stage:** 001.instance · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-003
- **Depends on:** `004.authentication-session`

## Definition
Gives the administrator their own area and the first page in it. The `admin` entry makes one identity round-trip before it mounts anything, so a non-administrator never sees an administrative frame at all — and a transport failure or a 5xx on that round-trip is a not-ready-yet state, never a deny. Inside it, the administrator creates accounts, disables and re-enables them, and resets passwords; disabling an account ends that user's live sessions immediately. The account list shows accounts and nothing else — no count, no title, no fragment of any roleplayer's material.

## Scope
**In:**
- the `admin` entry's boot gate and its three deny/not-ready cases
- the `AppShell` shell, the static nav table and the pure active-match function
- the 404 route
- the MobX shell-state class
- the Users page with create, disable, re-enable and password reset
- ending a disabled user's `auth_sessions` rows in the same transaction as the flag
- the shared confirm modal, first used for disabling an account

**Out:**
- the LLM Servers page (`006`)
- the Database page (`007`)
- the user-menu item that navigates here (`008`)
- the cross-cutting privacy audit (`032`)

## Open questions for the planner
- Whether a password reset sets a known value shown once to the administrator or forces a change at next login, which UC-008/US-010 do not fix.
- Whether the confirm modal is built here as a shared component or per page, given `006` and `007` both need it.
<!-- roadmap:end -->
