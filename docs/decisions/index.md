# Decision index

Registry of every `DEC` id. Regenerated from the entries on every write — never
edited independently of the files (`AGENTS.md`).

| Id | Title | Status | Feature | Stage |
|---|---|---|---|---|
| DEC-001-1 | The foundation conventions D1–D10 are held by the architecture | accepted | 001.backend-foundation | 001.instance |
| DEC-001-2 | `resolve_secret`'s read-side boundary rulings | accepted | 001.backend-foundation | 001.instance |
| DEC-001-3 | What a secret-pointer failure carries, and what the handler logs | accepted | 001.backend-foundation | 001.instance |
| DEC-001-4 | The handler is registered with the decorator form | accepted | 001.backend-foundation | 001.instance |
| DEC-001-5 | Any failure out of the extension loader becomes `ExtensionLoadError` | accepted | 001.backend-foundation | 001.instance |
| DEC-001-6 | The generator is built once, refuses an out-of-range node id, and reads an injected clock | accepted | 001.backend-foundation | 001.instance |
| DEC-001-7 | The health response field is `schema_` with the wire alias `schema` | accepted | 001.backend-foundation | 001.instance |
| DEC-001-8 | The app factory takes no parameters, and its collaborators are patchable names | accepted | 001.backend-foundation | 001.instance |
| DEC-002-1 | Stores and drafts are pure data; effects are free functions | accepted | 002.frontend-foundation | 001.instance |
| DEC-002-2 | The client decodes once; each draft maps its own fields | accepted | 002.frontend-foundation | 001.instance |
| DEC-002-3 | The remaining foundation decisions are held by the architecture | accepted | 002.frontend-foundation | 001.instance |
| DEC-002-4 | `vite.config.ts` resolves paths from `__dirname` | superseded by DEC-F008-6 | 002.frontend-foundation | 001.instance |
| DEC-002-5 | A minimal Mantine theme, dark by default | accepted | 002.frontend-foundation | 001.instance |
| DEC-002-6 | Vitest shares the Vite config, and build does not run tsc | accepted | 002.frontend-foundation | 001.instance |
| DEC-002-7 | API client request and response edges | accepted | 002.frontend-foundation | 001.instance |
| DEC-002-8 | The colour-scheme toggle names the action | accepted | 002.frontend-foundation | 001.instance |
| DEC-002-9 | Pinned dependency versions | accepted | 002.frontend-foundation | 001.instance |
| DEC-003-1 | Argon2id with library defaults, no rehash-on-verify | accepted | 003.first-run-bootstrap | 001.instance |
| DEC-003-2 | `already_configured` is 409 with no detail | accepted | 003.first-run-bootstrap | 001.instance |
| DEC-003-3 | "Configured" is defined once, in the bootstrap service | accepted | 003.first-run-bootstrap | 001.instance |
| DEC-003-4 | Pre-bootstrap health reads degraded, and only `configured` is branched on | accepted | 003.first-run-bootstrap | 001.instance |
| DEC-003-5 | The guard and the generator dependency live in the bootstrap router | accepted | 003.first-run-bootstrap | 001.instance |
| DEC-003-6 | `roles.py` is a leaf module holding the role enum | superseded in part by DEC-004-8 | 003.first-run-bootstrap | 001.instance |
| DEC-003-7 | Schema creation runs inside the creation transaction | accepted | 003.first-run-bootstrap | 001.instance |
| DEC-003-8 | Bootstrap sets no cookie and hands off to the login page | superseded by DEC-004-11 | 003.first-run-bootstrap | 001.instance |
| DEC-003-9 | The not-ready predicate | accepted | 003.first-run-bootstrap | 001.instance |
| DEC-003-10 | A fixed 2-second re-probe with no cap, and a manual retry | accepted | 003.first-run-bootstrap | 001.instance |
| DEC-003-11 | Bootstrap entry layout: no failure toast, stores beside `main.tsx` | accepted | 003.first-run-bootstrap | 001.instance |
| DEC-003-12 | The pure-data scan clause is deleted; the store convention is review-enforced | accepted | 003.first-run-bootstrap | 001.instance |
| DEC-003-13 | The whole `users` table is declared at once | accepted | 003.first-run-bootstrap | 001.instance |
| DEC-003-14 | The bootstrap form's credential rules | accepted | 003.first-run-bootstrap | 001.instance |
| DEC-004-1 | One uniform refusal, with a decoy verify | accepted | 004.authentication-session | 001.instance |
| DEC-004-2 | `invalid_credentials` is 400 | accepted | 004.authentication-session | 001.instance |
| DEC-004-3 | 401 versus 403, and authentication first | accepted | 004.authentication-session | 001.instance |
| DEC-004-4 | Absolute session expiry, never extended | accepted | 004.authentication-session | 001.instance |
| DEC-004-5 | Session tokens: random, stored as a SHA-256 digest | accepted | 004.authentication-session | 001.instance |
| DEC-004-6 | Cookie attributes | accepted | 004.authentication-session | 001.instance |
| DEC-004-7 | The role is read live on every request | accepted | 004.authentication-session | 001.instance |
| DEC-004-8 | Where the role ladder and the guards live | accepted | 004.authentication-session | 001.instance |
| DEC-004-9 | Logout is idempotent and needs no session | accepted | 004.authentication-session | 001.instance |
| DEC-004-10 | Route paths, and login answers with the identity | accepted | 004.authentication-session | 001.instance |
| DEC-004-11 | Bootstrap create signs the new admin in | accepted | 004.authentication-session | 001.instance |
| DEC-004-12 | No role branch after login | accepted | 004.authentication-session | 001.instance |
| DEC-004-13 | Credentials are not normalised | accepted | 004.authentication-session | 001.instance |
| DEC-004-14 | The login entry is one screen and does not probe on mount | superseded in part by DEC-F010-1, DEC-F010-3 | 004.authentication-session | 001.instance |
| DEC-004-15 | Login has a draft and no page store | accepted | 004.authentication-session | 001.instance |
| DEC-005-1 | Change Role is built, and the client never re-implements the refusal | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-005-2 | `last_login_at` is stamped inside the login transaction | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-005-3 | Account management lives in `services/users.py` | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-005-4 | Bulk session revoke on disable | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-005-5 | Named action routes under `/api/admin/users` | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-005-6 | An admin sets a password directly; non-empty is the only rule | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-005-7 | One shared confirm modal; only disable is confirmed | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-005-8 | The admin shell does not mount the colour-scheme toggle | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-005-9 | Path ids use the inbound alias | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-005-10 | Where a refusal renders in the user modals | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-005-11 | A back-to-app link and no user menu | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-005-12 | Three nav items, matched by whole path segment | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-005-13 | The access gate: five outcomes, 2-second retry while not ready | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-005-14 | The gate's classification is pure, and denial navigates through the seam | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-005-15 | MobX getters are forbidden | accepted | 005.admin-shell-and-users | 001.instance |
| DEC-006-1 | No "active" flag on a server registration | accepted | 006.llm-server-connections | 001.instance |
| DEC-006-2 | Designation measures the dimension with one real embeddings call | accepted | 006.llm-server-connections | 001.instance |
| DEC-006-3 | `httpx.AsyncClient` as the one outbound client | superseded by DEC-035-1 | 006.llm-server-connections | 001.instance |
| DEC-006-4 | Use-time embedding validation requires designated and enabled | superseded by DEC-006-5 | 006.llm-server-connections | 001.instance |
| DEC-006-5 | The embedding validator ignores `is_enabled` | accepted | 006.llm-server-connections | 001.instance |
| DEC-006-6 | `kind` is a label, never a dispatch key | superseded by DEC-arch-llm-client-library-1 | 006.llm-server-connections | 001.instance |
| DEC-006-7 | The four-value probe outcome, stored as the value itself | accepted | 006.llm-server-connections | 001.instance |
| DEC-006-8 | Statuses for the LLM error codes | accepted | 006.llm-server-connections | 001.instance |
| DEC-006-9 | Write-time pointer validation is a field type answering 422 | accepted | 006.llm-server-connections | 001.instance |
| DEC-006-10 | The pointer field: omitted, empty or a value | accepted | 006.llm-server-connections | 001.instance |
| DEC-006-11 | Enabling and disabling flip flags; rows are never deleted | accepted | 006.llm-server-connections | 001.instance |
| DEC-006-12 | Failed-probe resilience holds by construction | accepted | 006.llm-server-connections | 001.instance |
| DEC-006-13 | The validators take a plain server-and-model pair | accepted | 006.llm-server-connections | 001.instance |
| DEC-006-14 | A 30-second LLM request timeout | superseded by DEC-arch-llm-client-library-2 | 006.llm-server-connections | 001.instance |
| DEC-006-15 | The test route lets `secret_ref_missing` propagate as 500 | accepted | 006.llm-server-connections | 001.instance |
| DEC-006-16 | The admin LLM route surface and the designation's transaction | accepted | 006.llm-server-connections | 001.instance |
| DEC-006-17 | Only Delete and Clear Embedding are confirmed | accepted | 006.llm-server-connections | 001.instance |
| DEC-007-1 | What the report compares, and how both sides are normalised | accepted | 007.schema-drift-and-remediation | 001.instance |
| DEC-007-2 | Three statuses; `seed-missing` declined | accepted | 007.schema-drift-and-remediation | 001.instance |
| DEC-007-3 | The walk covers `metadata.tables` only | accepted | 007.schema-drift-and-remediation | 001.instance |
| DEC-007-4 | Create and Sync are defined by postcondition, so no "wrong state" error exists | accepted | 007.schema-drift-and-remediation | 001.instance |
| DEC-007-5 | The rebuild: Alembic batch recreate, inside one all-or-nothing transaction | accepted | 007.schema-drift-and-remediation | 001.instance |
| DEC-007-6 | `alembic` is a runtime dependency, used for batch operations only | accepted | 007.schema-drift-and-remediation | 001.instance |
| DEC-007-7 | The lossy-Sync confirm, and what the row menu offers | accepted | 007.schema-drift-and-remediation | 001.instance |
| DEC-007-8 | Foreign keys during a rebuild: off outside the transaction, on again in `finally` | accepted | 007.schema-drift-and-remediation | 001.instance |
| DEC-007-9 | Two error codes, the route surface, and where the table name is made safe | accepted | 007.schema-drift-and-remediation | 001.instance |
| DEC-007-10 | `/api/health`'s schema roll-up: missing > drift > ok, uncached | accepted | 007.schema-drift-and-remediation | 001.instance |
| DEC-007-11 | Status badge colours | accepted | 007.schema-drift-and-remediation | 001.instance |
| DEC-007-12 | The page store has no methods and no computed getters | accepted | 007.schema-drift-and-remediation | 001.instance |
| DEC-007-13 | The report table: two summary cells from one pure helper | accepted | 007.schema-drift-and-remediation | 001.instance |
| DEC-007-14 | After any apply the page re-loads the whole report | accepted | 007.schema-drift-and-remediation | 001.instance |
| DEC-008-1 | Identity lives in `shared/currentUser.ts` | accepted | 008.app-shell-frame | 002.record |
| DEC-008-2 | The boot gate: five outcomes, with 401 keyed on `not_authenticated` | accepted | 008.app-shell-frame | 002.record |
| DEC-008-3 | Re-probe timing: armed from each probe's completion | accepted | 008.app-shell-frame | 002.record |
| DEC-008-4 | Below 820px: always the rail; expand opens the same column as an overlay | accepted | 008.app-shell-frame | 002.record |
| DEC-008-5 | Dismissing the overlay | accepted | 008.app-shell-frame | 002.record |
| DEC-008-6 | The rail: "New character" and a Search trigger | accepted | 008.app-shell-frame | 002.record |
| DEC-008-7 | Six in-entry routes plus a 404 inside the shell | accepted | 008.app-shell-frame | 002.record |
| DEC-008-8 | The user menu and the logout failure posture | accepted | 008.app-shell-frame | 002.record |
| DEC-008-9 | The persisted layout record | accepted | 008.app-shell-frame | 002.record |
| DEC-008-10 | Shell state is written on the toggle; wide toggles write unconditionally | accepted | 008.app-shell-frame | 002.record |
| DEC-008-11 | `browserLayoutStorage` guards the `localStorage` getter | accepted | 008.app-shell-frame | 002.record |
| DEC-008-12 | The collapse glyph is `IconChevronLeft` | accepted | 008.app-shell-frame | 002.record |
| DEC-008-13 | The grid element is a raw `div` | accepted | 008.app-shell-frame | 002.record |
| DEC-008-14 | The boot-state module is `appBootState.ts`, not `appBoot.ts` | accepted | 008.app-shell-frame | 002.record |
| DEC-009-1 | The persona's explicit Save | superseded by DEC-018-7 | 009.characters | 002.record |
| DEC-009-2 | One shared TipTap wrapper, and the editor dependency pins | accepted | 009.characters | 002.record |
| DEC-009-3 | "Show archived" switch in the tree header, not persisted | accepted | 009.characters | 002.record |
| DEC-009-4 | The `characters` table as first declared | accepted | 009.characters | 002.record |
| DEC-009-5 | Router-level `require_user`; an admin is just another owner | accepted | 009.characters | 002.record |
| DEC-009-6 | PATCH semantics: null means absent, an empty PATCH is a no-op | accepted | 009.characters | 002.record |
| DEC-009-7 | One 404 for missing and foreign; stripped name; native 422 | accepted | 009.characters | 002.record |
| DEC-009-8 | Archive semantics: idempotent, keeps the original `archived_at` | accepted | 009.characters | 002.record |
| DEC-009-9 | Server list order: `created_at DESC, id DESC` | accepted | 009.characters | 002.record |
| DEC-009-10 | One workspace characters state; apply the returned row | accepted | 009.characters | 002.record |
| DEC-009-11 | Fixed failure sentences, no `notifyFailure` | accepted | 009.characters | 002.record |
| DEC-009-12 | Create hands the new id to a callback | accepted | 009.characters | 002.record |
| DEC-009-13 | Tree selection: `useMatch` outside `<Routes>`, explicit `aria-current` | accepted | 009.characters | 002.record |
| DEC-010-1 | Setups are a section of the character page; no setup route | accepted | 010.setups | 002.record |
| DEC-010-2 | Create and edit in a Modal with a fresh draft | accepted | 010.setups | 002.record |
| DEC-010-3 | Archiving a setup is always silent and always succeeds | accepted | 010.setups | 002.record |
| DEC-010-4 | "Show archived setups" switch, not persisted | accepted | 010.setups | 002.record |
| DEC-010-5 | Route surface: nested collection, flat single resource | accepted | 010.setups | 002.record |
| DEC-010-6 | The setups service checks the parent with its own scoped select | accepted | 010.setups | 002.record |
| DEC-010-7 | The `setups` table | accepted | 010.setups | 002.record |
| DEC-010-8 | Not-found and validation, as 009 | accepted | 010.setups | 002.record |
| DEC-010-9 | Archive semantics and order, as 009 | accepted | 010.setups | 002.record |
| DEC-010-10 | Section-owned state keyed by character id; a separate `applySetup` | accepted | 010.setups | 002.record |
| DEC-010-11 | Fixed failure sentences, no `notifyFailure` | accepted | 010.setups | 002.record |
| DEC-010-12 | The list is a plain table with one overflow menu per row | accepted | 010.setups | 002.record |
| DEC-011-1 | Starting a session is inline in the Sessions section | accepted | 011.rp-sessions | 002.record |
| DEC-011-2 | The create route: no opening message; setup checks | accepted | 011.rp-sessions | 002.record |
| DEC-011-3 | `last_used_at`: set at creation, bumped only by content writes | accepted | 011.rp-sessions | 002.record |
| DEC-011-4 | No title; the label is the start time | superseded by DEC-arch-session-names-1 | 011.rp-sessions | 002.record |
| DEC-011-5 | Archived sessions surface only on the character page | accepted | 011.rp-sessions | 002.record |
| DEC-011-6 | Tree characters are ordered by newest session use, client-side | accepted | 011.rp-sessions | 002.record |
| DEC-011-7 | The per-character chevron and its persisted collapse set | accepted | 011.rp-sessions | 002.record |
| DEC-011-8 | The `sessions` table as first declared | accepted | 011.rp-sessions | 002.record |
| DEC-011-9 | The route surface; no `PATCH` | superseded in part by DEC-arch-session-names-2 | 011.rp-sessions | 002.record |
| DEC-011-10 | `setup_name` by an owner-scoped LEFT JOIN, archived or not | accepted | 011.rp-sessions | 002.record |
| DEC-011-11 | RP-session naming avoids login-session vocabulary; no service imports | accepted | 011.rp-sessions | 002.record |
| DEC-011-12 | `session_not_found` 404, `setup_archived` 409, and the check order | accepted | 011.rp-sessions | 002.record |
| DEC-011-13 | Archive semantics; archive never moves `last_used_at` | accepted | 011.rp-sessions | 002.record |
| DEC-011-14 | Server order: `last_used_at DESC, id DESC` | accepted | 011.rp-sessions | 002.record |
| DEC-011-15 | Workspace `SessionsState` plus a section state; apply the row to both | accepted; superseded in part by DEC-034-12 | 011.rp-sessions | 002.record |
| DEC-011-16 | The tree's session level | accepted | 011.rp-sessions | 002.record |
| DEC-011-17 | The session screen's character link falls back to "Character" | accepted | 011.rp-sessions | 002.record |
| DEC-011-18 | Fixed failure sentences, including a non-blocking choices failure | accepted | 011.rp-sessions | 002.record |
| DEC-011-19 | Setup choices reload on every dropdown open | accepted | 011.rp-sessions | 002.record |
| DEC-011-20 | Build-time mechanisms: optional snowflake body, join operator, 24-hour format | accepted | 011.rp-sessions | 002.record |
| DEC-012-1 | The two "views" are Core selectables, not SQL VIEWs | accepted | 012.messages-and-settle | 002.record |
| DEC-012-2 | `PATCH /api/messages/{id}` edits current-zone rows only | superseded in part by DEC-014-1 and DEC-F014-10 | 012.messages-and-settle | 002.record |
| DEC-012-3 | Every content write bumps the session; one instant per operation | accepted | 012.messages-and-settle | 002.record |
| DEC-012-4 | No `session_vec` / FTS refresh in 012 | superseded by DEC-024-8 | 012.messages-and-settle | 002.record |
| DEC-012-5 | US-120 is answered by the product docs | accepted | 012.messages-and-settle | 002.record |
| DEC-012-6 | A third, text-free selectable for the edit target | accepted | 012.messages-and-settle | 002.record |
| DEC-012-7 | The `(( ))` classifier and strip rules | accepted | 012.messages-and-settle | 002.record |
| DEC-012-8 | `text` is required, non-blank, stored verbatim, with no maximum | accepted | 012.messages-and-settle | 002.record |
| DEC-012-9 | Re-open is the literal R11 rule | accepted | 012.messages-and-settle | 002.record |
| DEC-012-10 | Service isolation; settle and re-open return ids | accepted | 012.messages-and-settle | 002.record |
| DEC-012-11 | One router, `routers/stream.py`; settle and re-open take no target id | accepted | 012.messages-and-settle | 002.record |
| DEC-012-12 | Five new error codes: four 409s and one 404 | accepted | 012.messages-and-settle | 002.record |
| DEC-012-13 | A partner block may be filed over a zone draft | accepted | 012.messages-and-settle | 002.record |
| DEC-012-14 | R11's "two operations" read as a rule about the record columns | accepted | 012.messages-and-settle | 002.record |
| DEC-013-1 | Settle preview is a client-side port of the parens rules | accepted | 013.stream-and-zone-ui | 002.record |
| DEC-013-2 | Settle with composer text appends, then settles | accepted | 013.stream-and-zone-ui | 002.record |
| DEC-013-3 | Discard only for an empty zone with a blank composer | accepted | 013.stream-and-zone-ui | 002.record |
| DEC-013-4 | Re-open on the last entry; accepted imprecision | accepted | 013.stream-and-zone-ui | 002.record |
| DEC-013-5 | Bodies rendered with react-markdown; three MessageBody variants | accepted | 013.stream-and-zone-ui | 002.record |
| DEC-013-6 | Send appends to the zone without a model call | superseded by DEC-021-12 | 013.stream-and-zone-ui | 002.record |
| DEC-013-7 | Partner paste files immediately; a failed paste is not re-inserted | accepted | 013.stream-and-zone-ui | 002.record |
| DEC-013-8 | Default kind alternates; the override holds until the record changes | accepted | 013.stream-and-zone-ui | 002.record |
| DEC-013-9 | Composer geometry | superseded by DEC-F011-4 | 013.stream-and-zone-ui | 002.record |
| DEC-013-10 | Zone edit in place, committed on blur | accepted; blank-commit case superseded in part by DEC-F014-10 | 013.stream-and-zone-ui | 002.record |
| DEC-013-11 | Settled entries read-only, no copy | superseded by DEC-014-7 and DEC-014-11 | 013.stream-and-zone-ui | 002.record |
| DEC-013-12 | One "Current zone" divider | accepted | 013.stream-and-zone-ui | 002.record |
| DEC-013-13 | A sibling stream store, one per mount | accepted | 013.stream-and-zone-ui | 002.record |
| DEC-013-14 | streamApi holds the seven stream calls | accepted | 013.stream-and-zone-ui | 002.record |
| DEC-013-15 | Failure and busy posture | accepted | 013.stream-and-zone-ui | 002.record |
| DEC-013-16 | Client blank test uses JS trim | accepted | 013.stream-and-zone-ui | 002.record |
| DEC-013-17 | Load, re-read and abort rules | accepted | 013.stream-and-zone-ui | 002.record |
| DEC-014-1 | PATCH edits settled rows of every kind | accepted | 014.entry-editing-and-copy-out | 002.record |
| DEC-014-2 | A settled edit bumps the session | accepted | 014.entry-editing-and-copy-out | 002.record |
| DEC-014-3 | Paste-cost estimate and threshold | accepted | 014.entry-editing-and-copy-out | 002.record |
| DEC-014-4 | notifyWarning takes a closed set of ids | accepted | 014.entry-editing-and-copy-out | 002.record |
| DEC-014-5 | Warn on composer pastes, synchronously, before any filing | accepted | 014.entry-editing-and-copy-out | 002.record |
| DEC-014-6 | Entry actions revealed by opacity | accepted | 014.entry-editing-and-copy-out | 002.record |
| DEC-014-7 | Copy only on turns | accepted | 014.entry-editing-and-copy-out | 002.record |
| DEC-014-8 | A hand-written CommonMark-subset stripper | accepted | 014.entry-editing-and-copy-out | 002.record |
| DEC-014-9 | Copy-out stripping rules (authoritative) | accepted | 014.entry-editing-and-copy-out | 002.record |
| DEC-014-10 | Clipboard write with an execCommand fallback | accepted | 014.entry-editing-and-copy-out | 002.record |
| DEC-014-11 | Settled entry editor | accepted; blank-commit case superseded in part by DEC-F014-10 | 014.entry-editing-and-copy-out | 002.record |
| DEC-015-1 | Where notes are edited | accepted | 015.memos | 002.record |
| DEC-015-2 | Blank is never a stored state; clearing deletes | accepted | 015.memos | 002.record |
| DEC-015-3 | Orphan-scope check deferred | accepted | 015.memos | 002.record |
| DEC-015-4 | Sort-key allocation at the end | superseded by DEC-016-5 | 015.memos | 002.record |
| DEC-015-5 | Save on focus leave; apply a row only if not older | accepted | 015.memos | 002.record |
| DEC-015-6 | PATCH any subset; flags independent | accepted | 015.memos | 002.record |
| DEC-015-7 | Reach statements from flags, with a backend twin | accepted | 015.memos | 002.record |
| DEC-015-8 | An archived parent is a valid note target | accepted | 015.memos | 002.record |
| DEC-015-9 | The chain route lives in the memos router | accepted | 015.memos | 002.record |
| DEC-015-10 | Memos table shape | accepted | 015.memos | 002.record |
| DEC-015-11 | The one service-import exception | accepted | 015.memos | 002.record |
| DEC-015-12 | Not-found error and check order | accepted | 015.memos | 002.record |
| DEC-015-13 | New-note lifecycle | accepted; the entry point superseded in part by DEC-F012-2 / DEC-F012-4 | 015.memos | 002.record |
| DEC-015-14 | Flag icons and the disabled look | accepted; flag placement superseded in part by DEC-F012-2 | 015.memos | 002.record |
| DEC-015-15 | Body validation | accepted | 015.memos | 002.record |
| DEC-015-16 | Separate level and chain states per mount | accepted | 015.memos | 002.record |
| DEC-015-17 | Scope id on the wire | accepted | 015.memos | 002.record |
| DEC-015-18 | Memo service queries | accepted | 015.memos | 002.record |
| DEC-016-1 | The wall lives in the session screen | accepted | 016.note-wall | 002.record |
| DEC-016-2 | Pinned is persisted, open is not | accepted | 016.note-wall | 002.record |
| DEC-016-3 | Closed wall stays mounted, inert | accepted | 016.note-wall | 002.record |
| DEC-016-4 | Landmark naming; separate chain state | accepted | 016.note-wall | 002.record |
| DEC-016-5 | New notes are prepended | accepted | 016.note-wall | 002.record |
| DEC-016-6 | Reorder operation | accepted | 016.note-wall | 002.record |
| DEC-016-7 | Optimistic reorder with revert | accepted | 016.note-wall | 002.record |
| DEC-016-8 | Drag-and-drop with dnd-kit | accepted | 016.note-wall | 002.record |
| DEC-016-9 | New note gets focus | accepted | 016.note-wall | 002.record |
| DEC-016-10 | Wall icons and labels | accepted | 016.note-wall | 002.record |
| DEC-016-11 | Wall layout in shell.css; narrow revert in TS | accepted | 016.note-wall | 002.record |
| DEC-016-12 | apiPut through the shared request path | accepted | 016.note-wall | 002.record |
| DEC-017-1 | Model captured when a session is created | accepted | 017.session-configuration | 003.assistant |
| DEC-017-2 | Use-time check order | accepted | 017.session-configuration | 003.assistant |
| DEC-017-3 | A captured model reports level session | accepted | 017.session-configuration | 003.assistant |
| DEC-017-4 | Model stored as two columns | accepted | 017.session-configuration | 003.assistant |
| DEC-017-5 | One nullable boolean per tool per level | accepted | 017.session-configuration | 003.assistant |
| DEC-017-6 | Text normalisation in the request models | accepted | 017.session-configuration | 003.assistant |
| DEC-017-7 | The enabled set and its order | accepted | 017.session-configuration | 003.assistant |
| DEC-017-8 | Two pure resolvers | accepted | 017.session-configuration | 003.assistant |
| DEC-017-9 | Configuration as a sub-resource | superseded in part by DEC-arch-session-names-2 | 017.session-configuration | 003.assistant |
| DEC-017-10 | Set-time check | accepted | 017.session-configuration | 003.assistant |
| DEC-017-11 | Timestamps and empty patches | accepted | 017.session-configuration | 003.assistant |
| DEC-017-12 | Service-import exception for the registry | accepted | 017.session-configuration | 003.assistant |
| DEC-017-13 | One configuration router; a public models list | accepted | 017.session-configuration | 003.assistant |
| DEC-017-14 | User settings separate from /api/me | accepted | 017.session-configuration | 003.assistant |
| DEC-017-15 | User settings as an on-page form | accepted | 017.session-configuration | 003.assistant |
| DEC-017-16 | Session configuration bar | accepted | 017.session-configuration | 003.assistant |
| DEC-017-17 | sendBlockedReason | accepted | 017.session-configuration | 003.assistant |
| DEC-017-18 | Session config modal draft | accepted | 017.session-configuration | 003.assistant |
| DEC-017-19 | No notifications | accepted | 017.session-configuration | 003.assistant |
| DEC-017-20 | Character config calls deferred to 018 | accepted (closed by DEC-018-9) | 017.session-configuration | 003.assistant |
| DEC-017-21 | Setting<T> and the model select encoding | accepted | 017.session-configuration | 003.assistant |
| DEC-017-22 | Session config state loads and failures | accepted | 017.session-configuration | 003.assistant |
| DEC-018-1 | No kind switch or setup choice on the page composer | accepted; setup-choice half superseded by DEC-033-8 | 018.character-page | 003.assistant |
| DEC-018-2 | No reply from the page; a JSON route | superseded by DEC-F004-1 | 018.character-page | 003.assistant |
| DEC-018-3 | Create and seed in one transaction | accepted | 018.character-page | 003.assistant |
| DEC-018-4 | ComposerCore split | accepted; geometry superseded by DEC-F011-4, Send placement superseded by DEC-F011-1 | 018.character-page | 003.assistant |
| DEC-018-5 | Page composer send | accepted | 018.character-page | 003.assistant |
| DEC-018-6 | Draft page; create on name blur | accepted | 018.character-page | 003.assistant |
| DEC-018-7 | Blur-save of name and persona | accepted | 018.character-page | 003.assistant |
| DEC-018-8 | Notes as a reorderable grid | accepted; grid layout superseded by DEC-033-6 | 018.character-page | 003.assistant |
| DEC-018-9 | Character configuration block | accepted | 018.character-page | 003.assistant |
| DEC-018-10 | Section order | superseded by DEC-033-1 | 018.character-page | 003.assistant |
| DEC-018-11 | Archive toggles stay section-local | accepted | 018.character-page | 003.assistant |
| DEC-019-1 | The harness lives in `services/llm/frames.py` | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-2 | Seven frame value types, one encoder, and the wire JSON form | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-3 | Harness interface: `frame_stream` public, `sse_response` adds one header | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-4 | The persist rule and the order of a stream's ending | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-5 | A non-domain exception and a terminal-less exhaustion end as `llm_unreachable` | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-6 | Disconnect detection: one `finally`, a poll as backstop | accepted; superseded in part by DEC-035-7 | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-7 | The partial row is written on its own short-lived connection | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-8 | `append_assistant_message` is the one assistant-row write, with no blank check | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-9 | The consumer resolves to exactly one of four outcomes and never rejects | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-10 | `api.ts` exports its failure decoding; `sse.ts` does not duplicate it | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-11 | In-flight assistant text is a dedicated observable field, not a zone row | accepted; deferred question settled by DEC-022-6 | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-12 | The compose handle: one non-observable field, linked to the mount signal | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-13 | `busy` and streaming are separate; the derivations that read streaming | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-14 | What each consumer outcome does on the client | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-15 | `accepted`: clear the sent draft, re-read, keep re-reads ordered | accepted; narrowed by DEC-019-19 | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-16 | Pressing Settle mid-stream stops the compose first, then settles | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-17 | Accepted residual races after a stop | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-18 | Tool frames are parsed and ignored by the compose effect | superseded by DEC-022-7 | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-19 | A failed send whose text was already stored clears the draft; the retry is textless | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-019-20 | The send-blocked reason gates Send only, never Stop | accepted | 019.streaming-transport-and-stop | 003.assistant |
| DEC-020-1 | Settled history is tagged by kind, the tag followed by a line feed | accepted | 020.context-assembly | 003.assistant |
| DEC-020-2 | Six system sections; no setup description, character name or tool descriptions | accepted | 020.context-assembly | 003.assistant |
| DEC-020-3 | Tool rows are left out of the history | superseded by DEC-021-9 | 020.context-assembly | 003.assistant |
| DEC-020-4 | A missing language names English; the two languages fall back independently | accepted | 020.context-assembly | 003.assistant |
| DEC-020-5 | Empty parts are omitted; instruction sections are always present | accepted | 020.context-assembly | 003.assistant |
| DEC-020-6 | Forced-note selection reuses the chain; the renderer does not sort | accepted | 020.context-assembly | 003.assistant |
| DEC-020-7 | History is the settled entries and the zone merged by id | accepted | 020.context-assembly | 003.assistant |
| DEC-020-8 | The session is read first; only three of its fields are used | accepted | 020.context-assembly | 003.assistant |
| DEC-020-9 | Placement: a neutral renderer and a service with an import exception | accepted | 020.context-assembly | 003.assistant |
| DEC-020-10 | Fixed English prompt constants | accepted | 020.context-assembly | 003.assistant |
| DEC-020-11 | Assembly reads live with separate sub-reads | accepted | 020.context-assembly | 003.assistant |
| DEC-020-12 | No compaction or truncation of the context | accepted | 020.context-assembly | 003.assistant |
| DEC-021-1 | The route commits the text, then streams | accepted | 021.compose-loop-and-tools | 003.assistant |
| DEC-021-2 | A textless compose is the retry | accepted | 021.compose-loop-and-tools | 003.assistant |
| DEC-021-3 | Model resolution happens inside the source, after `accepted` | accepted | 021.compose-loop-and-tools | 003.assistant |
| DEC-021-4 | The think convention and the strip rule | accepted; superseded in part (the stream-wrapping half) by `llm-and-streaming.md` § Thinking | 021.compose-loop-and-tools | 003.assistant |
| DEC-021-5 | Offered tools: switched on and registered, in fixed order | accepted | 021.compose-loop-and-tools | 003.assistant |
| DEC-021-6 | The tool seam and its failure literals | accepted | 021.compose-loop-and-tools | 003.assistant |
| DEC-021-7 | Tool rows: written when the outcome is known, failure swallowed | accepted; superseded in part by DEC-arch-llm-client-library-5 (arguments) and DEC-022-3 (wire fields) | 021.compose-loop-and-tools | 003.assistant |
| DEC-021-8 | The settle head is the last non-tool row; tool rows are not editable | accepted | 021.compose-loop-and-tools | 003.assistant |
| DEC-021-9 | Tool rows are replayed one pair per row | accepted; supersedes DEC-020-3 | 021.compose-loop-and-tools | 003.assistant |
| DEC-021-10 | `chat_stream`: the streaming chat call | superseded by DEC-arch-llm-client-library-1, DEC-arch-llm-client-library-2, DEC-035-6, DEC-035-7 | 021.compose-loop-and-tools | 003.assistant |
| DEC-021-11 | The loop writes one assistant row per exchange | accepted; superseded in part by DEC-arch-llm-client-library-5, DEC-035-6, DEC-035-7 | 021.compose-loop-and-tools | 003.assistant |
| DEC-021-12 | Send on my turn composes; the zone text is optional | accepted | 021.compose-loop-and-tools | 003.assistant |
| DEC-021-13 | A tool failure is a 502 `tool_failed` | accepted | 021.compose-loop-and-tools | 003.assistant |
| DEC-021-14 | Opening a chat client, and an injectable factory | accepted; superseded in part by DEC-035-1 | 021.compose-loop-and-tools | 003.assistant |
| DEC-021-15 | Service-import exceptions for compose | accepted | 021.compose-loop-and-tools | 003.assistant |
| DEC-022-1 | The discussion is read per entry | accepted | 022.discussion-ui | 003.assistant |
| DEC-022-2 | The discussion is the entry's buried messages | accepted | 022.discussion-ui | 003.assistant |
| DEC-022-3 | Tool fields on the wire are derived from the stored payload | accepted; supersedes DEC-021-7's "not on the wire" half | 022.discussion-ui | 003.assistant |
| DEC-022-4 | The think parser and its worked examples | accepted | 022.discussion-ui | 003.assistant |
| DEC-022-5 | Thinking is open while live, collapsed once persisted | accepted | 022.discussion-ui | 003.assistant |
| DEC-022-6 | The live reply is read-only; tool blocks come before the text | accepted; settles DEC-019-11's deferred question | 022.discussion-ui | 003.assistant |
| DEC-022-7 | The live tool list | accepted; supersedes DEC-019-18 | 022.discussion-ui | 003.assistant |
| DEC-022-8 | Regenerate | accepted | 022.discussion-ui | 003.assistant |
| DEC-022-9 | Settle derivations ignore tool rows | accepted | 022.discussion-ui | 003.assistant |
| DEC-022-10 | The editor holds the raw text, think tags included | accepted | 022.discussion-ui | 003.assistant |
| DEC-022-11 | The Discussion group behind a record entry | accepted | 022.discussion-ui | 003.assistant |
| DEC-022-12 | No open-discussion control in the zone | accepted | 022.discussion-ui | 003.assistant |
| DEC-022-13 | Failure notice and retry reuse existing paths | accepted | 022.discussion-ui | 003.assistant |
| DEC-022-14 | Icons for tools, thinking, Regenerate and the chevron | accepted | 022.discussion-ui | 003.assistant |
| DEC-022-15 | Client tool fields are optional | accepted | 022.discussion-ui | 003.assistant |
| DEC-022-16 | 022 does not touch the composer | superseded by DEC-F011-1 | 022.discussion-ui | 003.assistant |
| DEC-023-1 | A translation is awaited whole, not streamed | accepted | 023.partner-translation | 003.assistant |
| DEC-023-2 | The model call reuses the streaming chat call and joins its content | superseded by DEC-arch-llm-client-library-1 | 023.partner-translation | 003.assistant |
| DEC-023-3 | The fallback target language, and the cache key | accepted | 023.partner-translation | 003.assistant |
| DEC-023-4 | Cancelling a translation; the probe before the cache write | accepted | 023.partner-translation | 003.assistant |
| DEC-023-5 | Failure mapping and messages | accepted | 023.partner-translation | 003.assistant |
| DEC-023-6 | Which entries can be translated | accepted | 023.partner-translation | 003.assistant |
| DEC-023-7 | The translations table | accepted | 023.partner-translation | 003.assistant |
| DEC-023-8 | Three phases; a hit needs no model | accepted; superseded in part by DEC-arch-llm-client-library-1 | 023.partner-translation | 003.assistant |
| DEC-023-9 | The stale-text guard | accepted | 023.partner-translation | 003.assistant |
| DEC-023-10 | Translation input is stripped of thinking | accepted | 023.partner-translation | 003.assistant |
| DEC-023-11 | Editing an entry deletes its translations | accepted | 023.partner-translation | 003.assistant |
| DEC-023-12 | The route and its own client-factory dependency | accepted | 023.partner-translation | 003.assistant |
| DEC-023-13 | One translation state per mount | accepted | 023.partner-translation | 003.assistant |
| DEC-023-14 | The client invalidates after every entry edit | accepted | 023.partner-translation | 003.assistant |
| DEC-023-15 | The translate control's label carries its state | accepted | 023.partner-translation | 003.assistant |
| DEC-024-1 | A synchronous bridge: one client and one embed call per write | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-2 | Search tables are ensured on write, outside the schema metadata | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-3 | No KNN `IN` push-down on snowflake keys | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-4 | Vector upsert is delete-then-insert; the key column is looked up | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-5 | FTS triggers and back-fill | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-6 | The session text that is embedded | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-7 | A blank memo body has no vector | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-8 | Strict authoring writes, degraded record-keeping writes | accepted; the caught set is now DEC-F005-1's | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-9 | The shared factory dependency and the embed timeout | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-10 | The coverage flag on the wire | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-11 | Which responses set the client flag | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-12 | Fan-out includes archived sessions; fail hard only when there is work | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-13 | No staleness marker | accepted; superseded in part by DEC-F005-2 | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-14 | Session full-text search is deferred | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-15 | Fan-out diffs against the stored value and runs last | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-16 | The coverage banner | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-17 | Embedding failure sentences for authoring writes | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-024-18 | Service-import guards narrowed for the index service | accepted | 024.embedding-lifecycle | 004.retrieval |
| DEC-025-1 | One port method over three typed scope variants | accepted | 025.hybrid-search-port | 004.retrieval |
| DEC-025-2 | No embedding model propagates; absent tables are empty | accepted | 025.hybrid-search-port | 004.retrieval |
| DEC-025-3 | A memo hit's level is `memo_scope` + `memo_scope_id`, the stored value passed through | accepted | 025.hybrid-search-port | 004.retrieval |
| DEC-025-4 | Fusion constants: `k = 60`, depth 50, ties by ascending id | accepted | 025.hybrid-search-port | 004.retrieval |
| DEC-025-5 | Early exits issue nothing | accepted | 025.hybrid-search-port | 004.retrieval |
| DEC-025-6 | `SearchHit`'s shape and defaults | accepted | 025.hybrid-search-port | 004.retrieval |
| DEC-025-7 | Memo snippets: FTS `snippet()` or the leading extract, same plain shape | accepted | 025.hybrid-search-port | 004.retrieval |
| DEC-025-8 | Filters first: each arm ranks inside an `IN (candidate subquery)` | accepted | 025.hybrid-search-port | 004.retrieval |
| DEC-025-9 | The owner predicate is in every statement; the base relation is built once | accepted | 025.hybrid-search-port | 004.retrieval |
| DEC-025-10 | Read posture: a local `_reading`, the embed inside the read window | accepted | 025.hybrid-search-port | 004.retrieval |
| DEC-025-11 | FTS query sanitising rules | accepted | 025.hybrid-search-port | 004.retrieval |
| DEC-025-12 | The lexical arm's statement | accepted | 025.hybrid-search-port | 004.retrieval |
| DEC-025-13 | The vector arm: exact L2 scan, check order, key-column map | accepted | 025.hybrid-search-port | 004.retrieval |
| DEC-025-14 | `search` lives in `hybrid.py`; memo arms run vector first; `limit` is required | accepted | 025.hybrid-search-port | 004.retrieval |
| DEC-026-1 | At most 8 hits, no paging | accepted | 026.memo-search-tool | 004.retrieval |
| DEC-026-2 | The chain predicate has one home, `chain_clause` | accepted | 026.memo-search-tool | 004.retrieval |
| DEC-026-3 | Placement, and the sync port under the async loop | accepted | 026.memo-search-tool | 004.retrieval |
| DEC-026-4 | The adapter-to-seam import cycle: `TYPE_CHECKING` plus a function-local import | accepted | 026.memo-search-tool | 004.retrieval |
| DEC-026-5 | What the model receives | accepted | 026.memo-search-tool | 004.retrieval |
| DEC-026-6 | The tool raises; the seam reports | accepted | 026.memo-search-tool | 004.retrieval |
| DEC-026-7 | Ids come only from `ToolScope` | accepted | 026.memo-search-tool | 004.retrieval |
| DEC-027-1 | The scope predicate: same character, not the current session, not archived | accepted | 027.session-search-tool | 004.retrieval |
| DEC-027-2 | At most 5 hits, no paging | accepted | 027.session-search-tool | 004.retrieval |
| DEC-027-3 | What the model receives: a header line and a tail excerpt per session | accepted | 027.session-search-tool | 004.retrieval |
| DEC-027-4 | The excerpt read is the tool's own owner-scoped hydration | accepted | 027.session-search-tool | 004.retrieval |
| DEC-027-5 | A whitespace-only settled entry is joined as stored (open divergence from 024) | open | 027.session-search-tool | 004.retrieval |
| DEC-027-6 | The tool raises; the seam reports | accepted | 027.session-search-tool | 004.retrieval |
| DEC-027-7 | Placement: search and excerpt read in one worker-thread call | accepted | 027.session-search-tool | 004.retrieval |
| DEC-027-8 | Ids come only from `ToolScope`; `setup_id` is unused | accepted | 027.session-search-tool | 004.retrieval |
| DEC-028-1 | Provider: the Google Custom Search JSON API, key in a header | accepted | 028.web-search-tool | 004.retrieval |
| DEC-028-2 | Credentials from the environment, directly, without the `RPHELPER_` prefix | accepted | 028.web-search-tool | 004.retrieval |
| DEC-028-3 | Unconfigured means not offered; the registry is built per request | accepted | 028.web-search-tool | 004.retrieval |
| DEC-028-4 | The provider seam | accepted | 028.web-search-tool | 004.retrieval |
| DEC-028-5 | Every failure is `ToolFailedError`, raised `from None` | accepted | 028.web-search-tool | 004.retrieval |
| DEC-028-6 | Only the query leaves; only `query` is read; the scope is unused | accepted | 028.web-search-tool | 004.retrieval |
| DEC-028-7 | Nothing logs the query, the results or the key; nothing is cached | accepted | 028.web-search-tool | 004.retrieval |
| DEC-028-8 | Timeout 10 s; 5 results | accepted | 028.web-search-tool | 004.retrieval |
| DEC-028-9 | Parsing the response, formatting the content, the query rule | accepted | 028.web-search-tool | 004.retrieval |
| DEC-028-10 | Test isolation sets both variables to `""` | accepted | 028.web-search-tool | 004.retrieval |
| DEC-028-11 | Third-party request logs are silenced by level in `app/logging.py` | accepted | 028.web-search-tool | 004.retrieval |
| DEC-028-12 | The `web_search` declaration is 021's and is unchanged | accepted | 028.web-search-tool | 004.retrieval |
| DEC-029-1 | An embedding failure fails the whole search | accepted | 029.my-search | 004.retrieval |
| DEC-029-2 | Matching per kind; no flag predicate on memos | accepted | 029.my-search | 004.retrieval |
| DEC-029-3 | Archived rows are included and flagged by their own `archived_at` | accepted | 029.my-search | 004.retrieval |
| DEC-029-4 | Landing targets, the query in the URL, the two triggers | accepted | 029.my-search | 004.retrieval |
| DEC-029-5 | One route, five fixed groups; blank `q` costs nothing | accepted | 029.my-search | 004.retrieval |
| DEC-029-6 | 20 per group; name order for unscored kinds | accepted; superseded in part by DEC-arch-session-names-5 (session group order) | 029.my-search | 004.retrieval |
| DEC-029-7 | Substring semantics for the name corpora | accepted; superseded in part by DEC-F006-4 (case folding) and DEC-F006-3 (how the fold is applied) | 029.my-search | 004.retrieval |
| DEC-029-8 | Hydration: one owner-scoped read per kind | accepted; superseded in part by DEC-034-8 (session and entry display keys) | 029.my-search | 004.retrieval |
| DEC-029-9 | Memo hydration reports `scope_id` as `null` for the user level | accepted | 029.my-search | 004.retrieval |
| DEC-029-10 | Execution order: model-opening calls first, then everything else | accepted | 029.my-search | 004.retrieval |
| DEC-029-11 | Read posture: a local `_reading` that rolls back only its own transaction | accepted | 029.my-search | 004.retrieval |
| DEC-029-12 | Presentation: archived and disabled markings, plain-text snippets | accepted | 029.my-search | 004.retrieval |
| DEC-029-13 | The landing URL contract | accepted | 029.my-search | 004.retrieval |
| DEC-029-14 | Focus on arrival; only `SessionScreen` reads the URL; page state per mount | accepted | 029.my-search | 004.retrieval |
| DEC-029-15 | The entry highlight: a Mantine `bg`, 2000 ms, one centred scroll | accepted | 029.my-search | 004.retrieval |
| DEC-029-16 | Response conversion follows the `MemoChainResponse` precedent | accepted | 029.my-search | 004.retrieval |
| DEC-029-17 | The search router is registered last; no "no SQL construct" guard for it | accepted | 029.my-search | 004.retrieval |
| DEC-029-18 | The tree's search box | accepted | 029.my-search | 004.retrieval |
| DEC-030-1 | What each granularity contains | accepted | 030.export-granularities | 005.portability |
| DEC-030-2 | The envelope's shape: no root header, two version numbers, a `TypedDict` | accepted | 030.export-granularities | 005.portability |
| DEC-030-3 | `SCHEMA_VERSION` starts at 1 and is bumped by hand | accepted; superseded in part by DEC-arch-session-names-7 (current value) | 030.export-granularities | 005.portability |
| DEC-030-4 | Row serialization is column-agnostic | accepted | 030.export-granularities | 005.portability |
| DEC-030-5 | The user export's exclusions are their own constants | accepted | 030.export-granularities | 005.portability |
| DEC-030-6 | The owned selections | accepted | 030.export-granularities | 005.portability |
| DEC-030-7 | Routes: placement, a raw `Response`, one header | accepted | 030.export-granularities | 005.portability |
| DEC-030-8 | `apiDownload` in the shared client | accepted | 030.export-granularities | 005.portability |
| DEC-030-9 | The admin Database page's Export action | accepted | 030.export-granularities | 005.portability |
| DEC-030-10 | The app's three export controls and the shared `runExport` | accepted | 030.export-granularities | 005.portability |
| DEC-031-1 | A session export is imported into a character the roleplayer chooses, with no setup | accepted | 031.import-and-id-remapping | 005.portability |
| DEC-031-2 | The whole-database import is a replace that preserves ids, allowed only on an empty or single-admin instance | accepted | 031.import-and-id-remapping | 005.portability |
| DEC-031-3 | No import embeds anything; full text is kept current inside the import | accepted | 031.import-and-id-remapping | 005.portability |
| DEC-031-4 | Import lives in a sibling service module, and the file travels as a JSON body | accepted | 031.import-and-id-remapping | 005.portability |
| DEC-031-5 | Envelope validation: five reasons in a fixed order, and every bad value refused before any write | accepted; superseded in part by DEC-arch-session-names-7 and DEC-034-7 (version 1 imports through one named upgrade) | 031.import-and-id-remapping | 005.portability |
| DEC-031-6 | The remap engine: ascending minting, one reference policy, a two-pass self-reference | accepted | 031.import-and-id-remapping | 005.portability |
| DEC-031-7 | Two payload rows sharing a primary key are `malformed_payload` | accepted | 031.import-and-id-remapping | 005.portability |
| DEC-031-8 | The database replace: the writer is called directly, and the vector tables are dropped, not cleared | accepted | 031.import-and-id-remapping | 005.portability |
| DEC-031-9 | The admin import handler is a bare delegation with no exception handling | accepted | 031.import-and-id-remapping | 005.portability |
| DEC-031-10 | Client import effects: one coverage warning through a new warning id, and a fixed reload scope | accepted | 031.import-and-id-remapping | 005.portability |
| DEC-031-11 | App entry points: reuse the existing sessions prop, a hidden input outside the menu, reset before dispatch | accepted | 031.import-and-id-remapping | 005.portability |
| DEC-031-12 | Admin Database page import: three fields, a derived confirm, no state written on success | accepted | 031.import-and-id-remapping | 005.portability |
| DEC-032-1 | Leak-fix policy: a small leak is fixed in the step that finds it; a redesign is handed back | accepted | 032.privacy-isolation-audit | 005.portability |
| DEC-032-2 | The sweep's one finding: the session-vector refresh resolves empty-text ids owner-scoped before deleting | accepted | 032.privacy-isolation-audit | 005.portability |
| DEC-032-3 | uvicorn access-log redaction: a filter on the logger, rewriting only the target's query | accepted | 032.privacy-isolation-audit | 005.portability |
| DEC-032-4 | Every log sink runs without diagnose or backtrace; the engine hides bound parameters | accepted | 032.privacy-isolation-audit | 005.portability |
| DEC-032-5 | The route-classification guard: a recursive walk, exact two-way equality, and no empty pass | accepted | 032.privacy-isolation-audit | 005.portability |
| DEC-032-6 | Unbuilt surfaces (rows 5 and 74): excluded by name and armed as absent | superseded by DEC-F002-1 and DEC-F003-1 (the row-5 shape guard survives) | 032.privacy-isolation-audit | 005.portability |
| DEC-032-7 | The fake model seam: one atomic install of the four override keys, and nothing else sets them | accepted | 032.privacy-isolation-audit | 005.portability |
| DEC-032-8 | Seeding order and payload shape follow the built validation; user content goes through the API only | accepted | 032.privacy-isolation-audit | 005.portability |
| DEC-032-9 | Sentinel carriers follow the real schema; sentinels are single lowercase alphanumeric tokens | accepted | 032.privacy-isolation-audit | 005.portability |
| DEC-032-10 | Witnesses narrowed to the real guarantee where the stated one was impossible | accepted | 032.privacy-isolation-audit | 005.portability |
| DEC-032-11 | Carve-outs are explicit, named and narrow | accepted | 032.privacy-isolation-audit | 005.portability |
| DEC-032-12 | Index snapshots read through `MATCH` or the `*_docsize` shadow tables, never a plain `SELECT` | accepted | 032.privacy-isolation-audit | 005.portability |
| DEC-032-13 | Admin sweep boundaries: the export excluded, the import only against the seeded world, matchers that cannot false-positive | accepted | 032.privacy-isolation-audit | 005.portability |
| DEC-032-14 | The log sweep is dynamic: no static scan of logger call sites | accepted | 032.privacy-isolation-audit | 005.portability |
| DEC-032-15 | Session and character list routes accept `include_archived`; the workspace store deliberately never sends it | accepted | 032.privacy-isolation-audit | 005.portability |
| DEC-033-1 | Five tabs, Sessions first and default; the active tab is component state | accepted | 033.character-page-tabs | — |
| DEC-033-2 | `keepMounted` stays at Mantine's default: every section loads once on open | accepted | 033.character-page-tabs | — |
| DEC-033-3 | The page header carries icon-only Archive/Restore and Export; busy means disabled | accepted | 033.character-page-tabs | — |
| DEC-033-4 | The Main info persona editor is taller, through an optional minimum height on the shared editor | accepted | 033.character-page-tabs | — |
| DEC-033-5 | The Configuration tab is the existing configuration section, moved as-is | accepted | 033.character-page-tabs | — |
| DEC-033-6 | Notes tab: a list with a header '+', reorder kept (the opt-in Save/Cancel mode superseded) | superseded in part by DEC-F012-2 | 033.character-page-tabs | — |
| DEC-033-7 | Setups tab: a header '+' opens an inline create form; edit stays in the modal | accepted | 033.character-page-tabs | — |
| DEC-033-8 | Sessions tab: composer with an optional setup choice, a divider, then the list with an icon Import | accepted | 033.character-page-tabs | — |
| DEC-033-9 | The message-less session start is removed | accepted | 033.character-page-tabs | — |
| DEC-033-10 | The composer's setup choice was accepted against the spec, and the spec amended | accepted | 033.character-page-tabs | — |
| DEC-034-1 | The rename body's `name`: a required key, string or null, normalised on both sides | accepted | 034.session-names | — |
| DEC-034-2 | `extra="forbid"` on the rename request model: the one named exception | accepted | 034.session-names | — |
| DEC-034-3 | No length cap on a session name | accepted | 034.session-names | — |
| DEC-034-4 | `sessions.name` is a privacy-audit content carrier; the rename route is an owner route | accepted | 034.session-names | — |
| DEC-034-5 | The name is not part of the embedded session text; a rename embeds nothing | accepted | 034.session-names | — |
| DEC-034-6 | `RpSession.name` defaults to None and is declared last | accepted; corrected in part by DEC-034-16 | 034.session-names | — |
| DEC-034-7 | The version-1 upgrade: the deserializer learns the file's version; only `sessions.name` may be absent | accepted | 034.session-names | — |
| DEC-034-8 | My-search wire keys and hydration: session hit `name`, entry hit `session_name`; name hits by name then id | accepted | 034.session-names | — |
| DEC-034-9 | The client label module: `sessionLabel`, a local-date fallback, `formatLocalDateTime` | accepted | 034.session-names | — |
| DEC-034-10 | Rename affordances: an `IconEdit` button on every tree session row and beside the header title | accepted | 034.session-names | — |
| DEC-034-11 | Rename editor semantics: unchanged sends nothing, one in flight, inline failure, apply the returned row | accepted | 034.session-names | — |
| DEC-034-12 | `applySession` orders `last_used_at` ties by id descending | accepted | 034.session-names | — |
| DEC-034-13 | The character page's Sessions list follows the workspace store by the apply-a-row rule | accepted | 034.session-names | — |
| DEC-034-14 | The workspace `SessionsState` is threaded to the session screen as a prop | accepted | 034.session-names | — |
| DEC-034-15 | Rename host rules: `onRenamed` never throws, and each host lifetime gets a fresh `SessionRenameState` | accepted | 034.session-names | — |
| DEC-034-16 | Correction: `RpSession.name` is the fifth of nine fields, after `setup_name`, with no default | accepted | 034.session-names | — |
| DEC-035-1 | The factory takes `kind` first; the gateway class is the production factory | accepted | 035.llm-client-gateway | — |
| DEC-035-2 | Probe value types move to the gateway; the delta types are deleted | accepted | 035.llm-client-gateway | — |
| DEC-035-3 | The gateway's test seam is a keyword-only map of library client classes | accepted | 035.llm-client-gateway | — |
| DEC-035-4 | `to_wire_message` is kept and builds the library's `messages` | accepted | 035.llm-client-gateway | — |
| DEC-035-5 | Library typing gaps are absorbed inside `gateway.py` only | accepted | 035.llm-client-gateway | — |
| DEC-035-6 | The chat-client protocol: `complete`, `compose`, and the tool bundle | accepted | 035.llm-client-gateway | — |
| DEC-035-7 | One unbounded queue, an end marker, and cancel-and-await on close | accepted | 035.llm-client-gateway | — |
| DEC-035-8 | How each operation maps library failures | accepted; superseded in part by DEC-035-20 (auth test), DEC-035-17 and DEC-arch-llm-client-library-15 (temporary-limitation cases), DEC-035-16 (exception set) | 035.llm-client-gateway | — |
| DEC-035-9 | Probe builds its library client with an empty model name | accepted | 035.llm-client-gateway | — |
| DEC-035-10 | `compose` uses the tool loop even when no tool is offered | accepted | 035.llm-client-gateway | — |
| DEC-035-11 | Base-URL normalisation rule | accepted | 035.llm-client-gateway | — |
| DEC-035-12 | Live tests port to the gateway, `kind` `llamaswap` | accepted | 035.llm-client-gateway | — |
| DEC-035-13 | Two unlisted probe-type importers move to the gateway in step 002 | accepted | 035.llm-client-gateway | — |
| DEC-035-14 | Five unlisted test modules follow step 002's interface | accepted | 035.llm-client-gateway | — |
| DEC-035-15 | Step 001 DoD-14's client-module identity check is retired with client.py | accepted | 035.llm-client-gateway | — |
| DEC-035-16 | Every exception out of the library, and a malformed tool declaration, surfaces as `llm_unreachable` / `unreachable` | accepted | 035.llm-client-gateway | — |
| DEC-035-17 | A model-side rejection reaches the compose source as its own stream value, `ComposeRejected` | accepted | 035.llm-client-gateway | — |
| DEC-035-18 | A model-side rejection is logged with the tool name and the kind only | accepted | 035.llm-client-gateway | — |
| DEC-035-19 | Explicit tool signatures stay under 0.2.1 | accepted | 035.llm-client-gateway | — |
| DEC-035-20 | The status-based auth split covers all four operations | accepted | 035.llm-client-gateway | — |
| DEC-F001-1 | The `/` seam is a copy in the image build, after a presence check | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-2 | No `location /app/` block | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-3 | Slash-less entry paths: exact-match locations returning a relative 302 | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-4 | `absolute_redirect off` at server level | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-5 | `location ^~ /api/` | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-6 | Path-only access log, declared inside the `server` block | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-7 | Deployment file layout and how the image installs its configs | accepted; compose layout superseded by DEC-F013-4 | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-8 | supervisord runs nginx and exactly one uvicorn, with no wait-for ordering | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-9 | `start.ps1`: two flags, two terminals, literal ports | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F002-1 | One blocking request; no job runner and no progress stream | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-2 | One transaction, all-or-nothing; the write lock is held across embedding | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-3 | The response is the fixed list of the four derived table names | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-4 | Always available; no designation fails with `no_embedding_model` | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-5 | Always drop and re-create both vector tables | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-6 | Order inside the transaction | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-7 | Chunked embedding with a fresh handle per chunk | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-8 | FTS: full rebuild for memos, record-rows-only refill for messages | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-9 | Placement: a service module, with public table helpers beside their constants | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-10 | Page-local confirm state; the confirm button is labelled "Rebuild" | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F003-1 | Schema creation and the import run in one transaction, through an extracted helper | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F003-2 | The restore route signs nobody in | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F003-3 | After the restore the operator is sent to `/login`; the environment notice is static copy | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F003-4 | The restore choice: a second offer item, no confirm modal (plan "Decision 4") | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F003-5 | Accepted consequences, deliberately not special-cased | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F003-6 | The restore's log line carries an outcome token only | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F003-7 | A native file input inside `Input.Wrapper`, not Mantine's `FileInput` | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F003-8 | `failureMessageOf` is exported from the restore module | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F004-1 | The session screen composes after arrival; the create route stays JSON | accepted | fast/004.character-page-first-reply | 006.repair |
| DEC-F004-2 | The trigger is a one-shot router-state marker, consumed on arrival | accepted | fast/004.character-page-first-reply | 006.repair |
| DEC-F004-3 | One textless compose through the existing path, at most once per stream state | accepted | fast/004.character-page-first-reply | 006.repair |
| DEC-F004-4 | Reload, or arriving mid-compose: no special handling | accepted | fast/004.character-page-first-reply | 006.repair |
| DEC-F004-5 | The page composer does not take a send-blocked reason | accepted | fast/004.character-page-first-reply | 006.repair |
| DEC-F005-1 | The caught set is a named tuple of three errors, not a base type | accepted | fast/005.degraded-embedding-path | 006.repair |
| DEC-F005-2 | A degraded write clears the session's vector, resolving its id owner-scoped first | accepted | fast/005.degraded-embedding-path | 006.repair |
| DEC-F006-1 | A registered SQLite function, not a stored folded column and not a collation | accepted | fast/006.unicode-name-matching | 006.repair |
| DEC-F006-2 | Registration sits between the sqlite-vec load and the PRAGMAs | accepted | fast/006.unicode-name-matching | 006.repair |
| DEC-F006-3 | Fold both sides and keep SQLAlchemy's autoescape, through one helper | accepted | fast/006.unicode-name-matching | 006.repair |
| DEC-F006-4 | Case folding only: no accent folding, no normalization | accepted | fast/006.unicode-name-matching | 006.repair |
| DEC-F006-5 | The session-name arm uses the same fold; correction of `DEC-arch-session-names-5` | accepted | fast/006.unicode-name-matching | 006.repair |
| DEC-F007-1 | Line shape, sink, and no prefix | accepted | fast/007.vite-proxy-request-log | — |
| DEC-F007-2 | Duration is measured to the response headers, not to the end | accepted | fast/007.vite-proxy-request-log | — |
| DEC-F007-3 | Start time from the earliest per-request event, keyed per request | accepted | fast/007.vite-proxy-request-log | — |
| DEC-F007-4 | At most one line per request | accepted | fast/007.vite-proxy-request-log | — |
| DEC-F007-5 | Redaction: path cut at `?` and `#`; an error carries its code only | accepted | fast/007.vite-proxy-request-log | — |
| DEC-F007-6 | Attach through the `/api` rule's `configure` hook; attaching is silent | accepted | fast/007.vite-proxy-request-log | — |
| DEC-F008-1 | A separate module; defaults shared with the proxy logger | accepted | fast/008.vite-dev-request-log | — |
| DEC-F008-2 | The skip rule mirrors the proxy's match exactly | accepted | fast/008.vite-dev-request-log | — |
| DEC-F008-3 | Duration to response end; status read at finish; an aborted request shows `-` | accepted | fast/008.vite-dev-request-log | — |
| DEC-F008-4 | A missing URL is logged, not skipped | accepted | fast/008.vite-dev-request-log | — |
| DEC-F008-5 | Registration: first in the chain, serve-only, silent, always `next()` | accepted | fast/008.vite-dev-request-log | — |
| DEC-F008-6 | `import.meta.dirname`, `.ts` specifiers, and `allowImportingTsExtensions` in both tsconfigs | accepted | fast/008.vite-dev-request-log | — |
| DEC-F009-1 | Plugin home, name and position | accepted | fast/009.vite-dev-root-routing | — |
| DEC-F009-2 | The routing predicate | accepted | fast/009.vite-dev-root-routing | — |
| DEC-F009-3 | Only `type="module"` script srcs are absolutized, by the plugin's own HTML hook | accepted | fast/009.vite-dev-root-routing | — |
| DEC-F009-4 | The request log keeps the browser's URL | accepted | fast/009.vite-dev-root-routing | — |
| DEC-F010-1 | The login probe leaves the form only on a strict `configured === false` (D1) | accepted | fast/010.unconfigured-to-bootstrap | — |
| DEC-F010-2 | The `{ configured }` reader stays entry-local in two places (D2) | accepted | fast/010.unconfigured-to-bootstrap | — |
| DEC-F010-3 | The probe's phase lives in a login-local MobX store (D3) | accepted | fast/010.unconfigured-to-bootstrap | — |
| DEC-F010-4 | The no-account guard's predicate is "any user exists", not `is_configured` (D4, amended) | accepted | fast/010.unconfigured-to-bootstrap | — |
| DEC-F010-5 | Placement: a guard in `dependencies.py`, its read in `services/bootstrap.py` (D4) | accepted | fast/010.unconfigured-to-bootstrap | — |
| DEC-F010-6 | Accepted cost: two small reads per cookie-bearing request | accepted | fast/010.unconfigured-to-bootstrap | — |
| DEC-F011-1 | Send is an icon-only control in the text box's bottom-right corner; Stop takes the same slot | accepted | fast/011.composer-send-icon-and-shortcut | — |
| DEC-F011-2 | The right section passes pointer events through except over the Send/Stop control | accepted | fast/011.composer-send-icon-and-shortcut | — |
| DEC-F011-3 | The dragged height is saved at drag end and restored on mount, per composer | accepted | fast/011.composer-send-icon-and-shortcut | — |
| DEC-F011-4 | Ctrl/Cmd+Enter sends when Send is shown and enabled; the text area is a fixed-rows, vertically resizable box | accepted | fast/011.composer-send-icon-and-shortcut | — |
| DEC-F012-1 | A flag click toggles only the flag; it does not save the body | accepted | fast/012.notes-autosave-toolbar-flags | — |
| DEC-F012-2 | One note behaviour supersedes plan 033's opt-in header-add mode | accepted | fast/012.notes-autosave-toolbar-flags | — |
| DEC-F012-3 | The shared markdown editor takes one optional trailing toolbar group | accepted | fast/012.notes-autosave-toolbar-flags | — |
| DEC-F012-4 | The note group's mechanics: header '+', focus-leave drafts, no Save/Cancel | accepted | fast/012.notes-autosave-toolbar-flags | — |
| DEC-F013-1 | The version comes from exactly one `vX.Y.Z` tag on HEAD | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F013-2 | `git tag --points-at HEAD`; two matching tags fail as ambiguous | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F013-3 | The store is `$DOCKER_STORE/rphelper` | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F013-4 | Compose restructure: dev takes the standard name; prod is image-based | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F013-5 | No `.env` templating; deploy refuses to restart without `.env` | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F013-6 | The archive is written to a temp file in the store and renamed on success | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F013-7 | `deploy.sh` mirrors BookWriter's `update.sh` | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F013-8 | Script conventions: strict mode, self-location, offline tests | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F014-1 | Build single-message delete now; the docs follow at finalization | accepted | fast/014.message-delete | — |
| DEC-F014-2 | Settled entries and current-zone messages are both deletable | accepted | fast/014.message-delete | — |
| DEC-F014-3 | A settled head takes its buried group with it, in the same transaction | accepted | fast/014.message-delete | — |
| DEC-F014-4 | The trash control confirms in red; a blank editor commit does not | accepted | fast/014.message-delete | — |
| DEC-F014-5 | Delete refusals mirror edit's — no new error code | accepted | fast/014.message-delete | — |
| DEC-F014-6 | 200 with `{deleted_ids, search_coverage_incomplete}`, not 204 | accepted | fast/014.message-delete | — |
| DEC-F014-7 | The service's order inside one transaction | accepted | fast/014.message-delete | — |
| DEC-F014-8 | Full-text upkeep follows the memo delete's placement | accepted | fast/014.message-delete | — |
| DEC-F014-9 | Frontend delete effects: never optimistic, never rejecting, never setting busy | accepted | fast/014.message-delete | — |
| DEC-F014-10 | A blank edit commit delegates to delete; unchanged text is a no-op | accepted | fast/014.message-delete | — |
| DEC-F014-11 | Trash icon placement, labels and gating | accepted | fast/014.message-delete | — |
| DEC-F014-12 | What single-message delete deliberately does not do | accepted | fast/014.message-delete | — |
| DEC-F014-13 | The trash control's disabled condition, and its untested half | accepted | fast/014.message-delete | — |
| DEC-F015-1 | Build the pending indicator in code; no product or architecture change now | accepted | fast/015.translate-pending-indicator | — |
| DEC-F015-2 | While pending, the flicker's glyph is a spinning loader instead of the language icon | accepted | fast/015.translate-pending-indicator | — |
| DEC-F015-3 | Label and accessibility semantics are unchanged while pending | accepted | fast/015.translate-pending-indicator | — |
| DEC-F015-4 | An entry's actions group is revealed while that entry's translation is pending | accepted | fast/015.translate-pending-indicator | — |
| DEC-F016-1 | Build the own-text tone in code; no product or architecture change now | accepted | fast/016.own-text-muted | — |
| DEC-F016-2 | The user-role row body is wrapped in a Mantine `Box` with `c="dimmed"` | accepted | fast/016.own-text-muted | — |
| DEC-F016-3 | Settled entries, the live reply and accent chips keep their colours | accepted | fast/016.own-text-muted | — |
| DEC-F016-4 | Test hook: `data-tone="muted"` on the wrapper | accepted | fast/016.own-text-muted | — |
| DEC-arch-llm-client-library-1 | Adopt `llm-client` 0.2.0 as a git dependency; Responses clients only, selected by `kind` | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-2 | One timeout: total time per request, default 600 s | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-3 | `auth_failed` is read from the library error's message | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-4 | The tool-loop cap is `max_loops=sys.maxsize` | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-5 | Minted call ids, and the persisted `arguments` | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-6 | Each wrapper carries an explicit signature from its declaration | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-7 | The wrapper never raises a tool's exception into the library | accepted; temporary-limitation clause superseded by DEC-arch-llm-client-library-15 | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-8 | How a compose exchange ends | accepted; temporary-limitation clause superseded by DEC-arch-llm-client-library-15 | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-9 | An OpenAI server with no credential | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-10 | Logging: the `aiohttp` logger tree is silenced | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-11 | Testing: fakes at the gateway/factory level | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-12 | No reasoning options are sent by default | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-13 | Pin `llm-client` `v0.2.1` | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-14 | `compose` passes `tool_errors="result"` explicitly | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-15 | Model-side tool mistakes become tool frames through the observer | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-16 | `auth_failed` is read from `LLMError.status` | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-17 | 0.2.1 options left unused: `read_timeout`, the trace switch, the provider call id | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-session-names-1 | Name storage: a nullable column, the default label computed by the client | accepted | arch-session-names | — |
| DEC-arch-session-names-2 | Route shape: a general `PATCH` that accepts `name` only | accepted | arch-session-names | — |
| DEC-arch-session-names-3 | Last-use display: local `YYYY-MM-DD HH:MM`, fixed width | accepted | arch-session-names | — |
| DEC-arch-session-names-4 | Rename interaction: in-place edit of the label | accepted; refined in part by DEC-034-11 (inline failure; the returned session is applied) | arch-session-names | — |
| DEC-arch-session-names-5 | My-search's session name arm: `LIKE`, merged ahead of vector hits | accepted; superseded in part by DEC-F006-5 (the D-05 case caveat) | arch-session-names | — |
| DEC-arch-session-names-6 | A rename bumps `updated_at` only | accepted | arch-session-names | — |
| DEC-arch-session-names-7 | Import accepts `schema_version` 1 through one named upgrade | accepted | arch-session-names | — |
