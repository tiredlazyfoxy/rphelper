# 032.privacy-isolation-audit — Privacy isolation audit
<!-- roadmap:start -->
- **Stage:** 005.portability · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-019
- **Depends on:** `026.memo-search-tool`, `027.session-search-tool`, `029.my-search`, `030.export-granularities`, `031.import-and-id-remapping`, `005.admin-shell-and-users`

## Definition
Proves the guarantee the whole product rests on, across every surface that now exists. No screen, listing, search, tool or export view reaches another user's material, and administrative surfaces expose no user content at all — not a title, not a fragment, and not a count derived from any of it. This is the cross-cutting audit, not the first time isolation is implemented: every content feature scoped its own owner predicate. What lands here is the systematic sweep that proves it, and the repair of anything the sweep finds.

## Scope
**In:**
- an enumeration of every listing, search, tool and administrative surface with the owner or role predicate each is asserted to apply
- a test suite that attempts a cross-user read through each of them and requires refusal or an empty result
- the forbidden reverse lookup asserted explicitly
- the assertion that no administrative response carries a count derived from user content
- the assertion that no log record at any level carries forbidden text
- fixes for any leak found

**Out:**
- re-designing any surface
- the whole-database export's opacity rule, which is `030`'s and is cited here rather than re-implemented

## Open questions for the planner
- Whether a found leak is fixed inside this feature or handed back as a bug against the feature that owns the surface — the scope above assumes the former for anything small.
<!-- roadmap:end -->
