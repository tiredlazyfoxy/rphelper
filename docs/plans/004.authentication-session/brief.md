# 004.authentication-session — Authentication and session
<!-- roadmap:start -->
- **Stage:** 001.instance · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-002
- **Depends on:** `003.first-run-bootstrap`

## Definition
Lets a created user log in, hold a session across requests and entries, and log out. A correct credential pair establishes an HttpOnly `SameSite=Lax` cookie session; a wrong pair and a disabled account are both refused, and the refusal does not tell an attacker which it was. When a session ends or expires the roleplayer is returned to the login screen from wherever they were. Because the cookie is same-origin it travels across all four entries automatically, which is what lets the entries share no authentication code at all.

## Scope
**In:**
- the `auth_sessions` table
- the login, logout and session-refresh routes
- the cookie's flags and lifetime
- `GET /api/me` returning the caller's identity and role
- the two-rung role ladder and the `require_role(min_role)` router dependency
- the `login` entry's form and its error states
- the return-to-login behaviour on an expired session

**Out:**
- creating, disabling or resetting accounts (`005`)
- the admin gate's frontend behaviour (`005`)
- the user menu's logout affordance (`008`)

## Open questions for the planner
- The session lifetime and whether it slides on activity, which no product id fixes.
- Whether `require_role` reads the role from the session row or re-reads `users` on every request, which decides how fast a role change or a disable takes effect.
<!-- roadmap:end -->
