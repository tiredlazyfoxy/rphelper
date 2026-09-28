# fast/003.bootstrap-from-export — Bootstrap from export
<!-- roadmap:start -->
- **Stage:** 005.portability · **Track:** fast · **Size:** S
- **Delivers:** FEAT-001 (UC-002, US-002)
- **Depends on:** `031.import-and-id-remapping`, `003.first-run-bootstrap`

## Definition
Closes the half of first-run that was deferred until an importer existed. Facing an unconfigured instance, the operator supplies a whole-database export instead of creating a fresh database, and the instance comes up holding it — users, characters, sessions and notes included. The instance is configured afterwards, so the bootstrap surface refuses to act again exactly as it does after the create-fresh path. Credentials do not travel in an export, so the environment has to be supplied separately for the restored instance to reach any model server.

## Scope
**In:**
- the second choice on the bootstrap screen
- accepting the export upload
- creating the database, applying the registry and running the whole-database import in one operation
- the refusal once configured
- telling the operator that the environment must be supplied separately

**Out:**
- the import machinery itself (`031`)
- any partial-granularity import at bootstrap

## Open questions for the planner
None.
<!-- roadmap:end -->
