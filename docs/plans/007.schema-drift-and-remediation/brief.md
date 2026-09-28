# 007.schema-drift-and-remediation — Schema drift and remediation
<!-- roadmap:start -->
- **Stage:** 001.instance · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-005 (UC-014, UC-015, US-017, US-018)
- **Depends on:** `005.admin-shell-and-users`

## Definition
Lets the administrator see whether the database's real shape matches what the code expects, and fix it when it does not. The Database page reports per table whether it is present, missing or differs, by introspecting the live file against the table-definition registry. Per-row create and sync actions apply the difference — a create for a missing table, a rebuild for one whose columns have changed, since SQLite cannot retype or drop a column in place. This is the only path by which the schema ever changes: there is no migration history and no automatic upgrade at startup.

## Scope
**In:**
- PRAGMA-based introspection against the registry
- the per-table drift report and its statuses
- the DDL executor built on Alembic batch operations, triggered only from this page
- the Database page's report table and its create and sync actions
- the administrator-facing result of a failed apply

**Out:**
- the vector-index rebuild, UC-016 / US-019 — deferred to `fast/002.vector-index-rebuild`, which has no vectors to rebuild until stage 004
- the export and import controls on the same page (`030`, `031`)

## Open questions for the planner
- What counts as "differs" — column set, types, nullability, defaults, indexes — since the report's granularity is the administrator's whole signal.
- Whether a sync that would lose data refuses or warns, which no acceptance criterion fixes.
<!-- roadmap:end -->
