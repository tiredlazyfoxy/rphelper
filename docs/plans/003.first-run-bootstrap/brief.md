# 003.first-run-bootstrap — First-run bootstrap
<!-- roadmap:start -->
- **Stage:** 001.instance · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-001 (UC-001, UC-003, US-001, US-003)
- **Depends on:** `001.backend-foundation`, `002.frontend-foundation`

## Definition
Lets someone facing an unconfigured instance turn it into a usable one. The `bootstrap` entry detects that no database and no users exist, offers to create a database with a first administrator, and creates both. Once the instance is configured the bootstrap surface refuses to act at all, so it can never be used a second time to mint an administrator. Because the entry runs before a schema exists it shares none of the authenticated shell's stores or session assumptions, and it renders a not-ready-yet state rather than an error while the backend is still coming up.

## Scope
**In:**
- the `users` table
- the bootstrap router and service
- the unconfigured-instance probe
- creating the database file, applying the registry and inserting the first administrator in one operation
- password hashing
- the refusal once configured
- the `bootstrap` entry's UI including the not-ready-yet state for a 502 or transport failure on its probe

**Out:**
- UC-002 / US-002, bringing an instance up from an existing export — deferred to `fast/003.bootstrap-from-export`
- logging in (`004`)
- any further account management (`005`)

## Open questions for the planner
- What exactly "configured" is read from — the presence of the database file, the presence of the `users` table, or a non-empty `users` table — given UC-003 must refuse in every case an administrator already exists.
- Which password hashing algorithm and parameters, which `docs/architecture/` does not fix.
<!-- roadmap:end -->
