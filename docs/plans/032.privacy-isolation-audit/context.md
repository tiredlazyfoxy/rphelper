# Feature 032 — privacy-isolation-audit — feature-wide context

## Goal and boundary

Deliver FEAT-019 (UC-065, UC-066; US-083.AC-1, US-084.AC-1, US-085.AC-1) as a
**systematic audit**, not a first implementation. Every content feature
(001..031) already scoped its own owner predicate; this feature proves the
guarantee across every surface in one place and repairs what the proof finds.
`brief.md` (this folder) is the agreed boundary. Do not edit it.

**In:** the enumeration below; a cross-user sweep through every surface; the
R5 reverse lookup asserted explicitly; no administrative response carries a
count derived from user content; no log record at any level carries forbidden
text; fixes for any leak found.

**Out:** redesigning any surface. The whole-database export's **opacity rule**
belongs to 030 and is cited, never re-implemented or re-tested here:
`docs/plans/030.export-granularities/context.md` (~L121), 030/005 DoD-2..4,
030/008 DoD-7. 032 only re-asserts the admin export/import **role gate** (via
the enumeration table) and the admin import's refusal shape.

Requirements are cited by id; open the product files for wording:
`docs/product/stories/FEAT-019.privacy-isolation.md`,
`docs/product/use-cases/FEAT-019.privacy-isolation.md`.

**Citation mapping for logs.** Operator-facing logs (console, supervisord, the
log file) are an administrative surface for the purpose of this audit, so every
log-redaction `[test]` item cites **US-084.AC-1**, with
`docs/architecture/deployment.md` "The redaction rule" as the mechanism.

## Architecture to hold

- `docs/architecture/domain-rules.md` **R5** — every read path scoped by owning
  user at query level from the authenticated session; no `model → dependent
  sessions` endpoint, count, badge, tooltip, `detail` field or confirm text; the
  whole-DB export is opaque. **R9** — the assistant's reach is exactly three
  tools, each a scoped read path.
- `docs/architecture/deployment.md` "The redaction rule" (forbidden list,
  allowed list, no level exception) and the `diagnose` paragraph.
- `docs/architecture/backend-structure.md` — typed error envelope, `require_user`
  / `require_role`, the JSON id boundary (ids are decimal strings).
- `docs/architecture/admin-surfaces.md` — the three admin pages.
- `docs/architecture/search-and-retrieval.md` — hybrid search, the three search
  surfaces (my-search is the owner's own UI and legitimately shows disabled
  memos — R3; that is not a leak).
- `docs/architecture/llm-and-streaming.md` — compose, tool loop, failure frames.

## Build state this plan is written against

- 001..017 are **built**; their routes and error codes below are harvested from
  source.
- 018..031 are **planned**; 032 builds **last**, after all of them. Their surfaces
  below come from their step files' Interface intent and DoD. Exact callable
  names for their services (e.g. 025's hybrid variants, 021's `build_tool_scope`,
  the LLM/embedding client-factory seam of 019/021) are taken from the
  `## Skeleton` section of the owning feature's `status.md` — the frozen
  signature record, which every role may read.
- `fast/002` (vector rebuild) and `fast/003` (bootstrap from export) have only a
  `brief.md` at plan time. Wherever this plan needs their route or payload, it
  says `_TBD: resolved from fast/00N plan.md at build time_`; the harvest for the
  step that touches them reads that `plan.md` (and its `status.md` `## Skeleton`).

## The audit-step convention (read before running the pipeline)

Steps 002..007 assert properties the built code is **expected to already
satisfy**. Their red gate therefore differs from the normal one:

- **Red gate for an audit step** = tests compile/import, every `[test]` item is
  covered and cited, and the tests run. "Fails for the right reason" does not
  apply: no leak means nothing to fail.
- **A test that FAILS against built code is a leak finding**, not a test defect
  (unless the verifier judges the test wrong → `TEST`). The finding is routed to
  the coder, whose scope is the step's **fix-allowance** (its Source files list).
- **A step whose tests all pass** is `done` with Files Changed = none.
- **Skeleton for audit steps is a no-op**, except step 002 (see `002.context.md`)
  where the skeleton freezes the support module's signatures and the exact
  methods/paths the enumeration leaves open.
- **Air gap holds:** expected outcomes (class, status, error code, empty/absent)
  come from the enumeration table and DoD here, never from code. The skeleton
  record tells the test-coder only *how to call*.

Step 001 is the exception: it is a real source change with a normal red gate
(the three leaks below exist today).

## Leak-fix policy (user-confirmed)

- A **small** leak (an owner predicate missing from one query, a field dropped
  from a response, a log call that formats content) is fixed inside the step
  that finds it, within that step's 200-LoC source budget and its
  fix-allowance.
- Anything that needs a **surface redesign** (a route's shape, a table's
  ownership model, a feature's contract) or falls outside the fix-allowance is
  **not** fixed here: the coder records it in `status.md` Notes & Issues and the
  orchestrator hands it back as a `/bug-fixer` run against the owning feature
  (column "Owner" in the table below). The step is then `blocked` on that item.

### Leaks already found at plan time (fixed in step 001)

1. uvicorn's access log records `METHOD path?query`, and 029's
   `GET /api/search?q=<text>` puts user text in the query string.
2. The console (stderr) loguru sink runs with loguru's default `diagnose=True`,
   so a traceback renders frame locals (message text, memo bodies, keys).
3. The engine has no `hide_parameters`; bound values would surface if the
   `sqlalchemy` logger level were lowered or a statement error were rendered.
   No current leak (the `sqlalchemy` logger sits at WARNING) — defence in depth.

Out of reach of this feature: **nginx's own `access_log` also records query
strings** (deployment surface, `fast/001`). Recorded for the architect in
`outcome.md`; not fixed here.

## Known risks the sweep may surface

- **fast/002 progress/response counts.** The brief forbids "a count derived from
  any of it". If fast/002's `plan.md` declares a vector/row count in the rebuild
  response or progress payload, that is a **finding**: drop the field if small
  (step 006 fix-allowance), else hand back against fast/002.
- **Inconsistent-owner rows.** `messages.user_id` is not constrained to equal the
  parent `sessions.user_id` (built schema), and `memos.scope_id` has no FK.
  Isolation rests on the owner predicate in every query. **No API path can write
  an inconsistent row** (every write derives `user_id` from the session and
  resolves parents owner-scoped), so no test seeds one by direct insert — it is
  not an attack path. Recorded in `outcome.md` as a data-model observation.
- **Admins are not super-readers.** An admin calling a user-content route sees
  only content they own (owner = the admin's own user id). Step 003 asserts it.

## Shared vocabulary

- **A, B** — two roleplayers; **ADM** — an admin; **anon** — no cookie.
  Every sweep makes A (or ADM) reach for B's material.
- **Foreign id** — an id that exists but belongs to another user.
- **Unknown id** — a well-formed id that exists nowhere, e.g.
  `"7250000000000000002"`.
- **Refusal identity** — for an owner-scoped route, the response to a foreign id
  equals the response to an unknown id: same status (404), same error `code`,
  `detail == {}`, identical JSON body. Nothing about the foreign row is
  distinguishable.
- **Sentinel** — a unique marker string seeded into one field of one table for
  one user. Sentinels are single lowercase alphanumeric tokens (no spaces,
  hyphens or punctuation) so FTS5 tokenizes each as one term and a LIKE/hybrid
  search can target it, e.g. `sntlbcharpersona`. Usernames, server names and
  model names are administrative data and **never** carry a sentinel.
- **Positive control** — every absence assertion is paired with the owner
  reaching the same material through the same surface, so an absence can never
  pass vacuously (empty because nothing was seeded).

## Classes used by the enumeration

| Class | Auth | Cross-user expectation |
|---|---|---|
| `public` | none | carries no sentinel; not a content surface |
| `self` | `require_user` | acts only on the caller's rows; response carries no other user's sentinel or id |
| `registry` | `require_user` | instance-wide administrative data (model registry); no sentinel |
| `owner` | `require_user` | foreign id ⇒ refusal identity with the listed 404 code; no write happens |
| `admin` | `require_role(ADMIN)` | anon ⇒ 401 `not_authenticated`; roleplayer ⇒ 403 `insufficient_role`; responses carry no user content and no count derived from it |

Every non-`public` route refuses anon with 401 `not_authenticated`. No route
takes a user id from body or query.

## The enumeration — every route, its predicate and its foreign-id outcome

This table **is** the brief's enumeration deliverable and the literal that step
002's route-classification guard compares `app.routes` against. Paths are
written with parameters normalized to `{}` (parameter names are irrelevant to
the guard). A method of `†` means "as built — frozen by step 002's skeleton
record"; the class and expected outcome are fixed here regardless. The
**Sweep** column names the step that asserts the row's cross-user behaviour
(002 asserts auth/role gates for every row).

| # | Method | Path | Class | Foreign / cross-user outcome | Owner | Sweep |
|---|---|---|---|---|---|---|
| 1 | GET | `/api/health` | public | no sentinel; unchanged by content | 001 | 006 |
| 2 | POST | `/api/bootstrap/create` | public | 409 `already_configured` once configured | 003 | 007 |
| 3 | POST | `/api/auth/login` | public | — | 004 | 007 |
| 4 | POST | `/api/auth/logout` | public | — | 004 | — |
| 5 | _TBD: fast/003 plan.md_ | _TBD: bootstrap-from-export path, fast/003 plan.md_ | public | 409 `already_configured` once configured; nothing wiped; no payload echoed | fast/003 | 005 |
| 6 | GET | `/api/me` | self | caller's own account only | 004 | 003 |
| 7 | GET | `/api/me/settings` | self | caller's own settings only | 017 | 003 |
| 8 | PATCH | `/api/me/settings` | self | writes caller's own row only | 017 | 003 |
| 9 | GET | `/api/models` | registry | no sentinel | 017 | 003 |
| 10 | GET | `/api/characters` | self | lists (incl. archived view) contain no B row | 006 | 003 |
| 11 | POST | `/api/characters` | self | created row owned by caller | 006 | 003 |
| 12 | GET | `/api/sessions` | self | no B row | 011 | 003 |
| 13 | GET | `/api/memos` | self | B's `scope_id` ⇒ empty list or 404, never B's memos | 015 | 003 |
| 14 | POST | `/api/memos` | self | B's `scope_id` ⇒ 404 or an inert row owned by caller; never visible to B by any surface | 015 | 003 |
| 15 | PUT | `/api/memos/order` | self | any B id in the order ⇒ 409 `memo_order_mismatch`, nothing reordered | 016 | 003 |
| 16 | GET | `/api/search` | self | all five groups exclude B's material | 029 | 004 |
| 17 | GET | `/api/export` | self | export carries no B row, sentinel or id | 030 | 005 |
| 18 | POST | `/api/import` | self | every imported row owned by caller whatever the payload says; B untouched | 031 | 005 |
| 19 | GET | `/api/characters/{}` | owner | 404 `character_not_found` | 006 | 003 |
| 20 | PATCH | `/api/characters/{}` | owner | 404 `character_not_found` | 006 | 003 |
| 21 | † | `/api/characters/{}/archive` | owner | 404 `character_not_found` | 006 | 003 |
| 22 | † | `/api/characters/{}/restore` | owner | 404 `character_not_found` | 006 | 003 |
| 23 | GET | `/api/characters/{}/setups` | owner | 404 `character_not_found` | 007 | 003 |
| 24 | POST | `/api/characters/{}/setups` | owner | 404 `character_not_found` | 007 | 003 |
| 25 | GET | `/api/setups/{}` | owner | 404 `setup_not_found` | 007 | 003 |
| 26 | PATCH | `/api/setups/{}` | owner | 404 `setup_not_found` | 007 | 003 |
| 27 | † | `/api/setups/{}/archive` | owner | 404 `setup_not_found` | 007 | 003 |
| 28 | † | `/api/setups/{}/restore` | owner | 404 `setup_not_found` | 007 | 003 |
| 29 | GET | `/api/characters/{}/sessions` | owner | 404 `character_not_found` | 011 | 003 |
| 30 | POST | `/api/characters/{}/sessions` | owner | B's character ⇒ 404 `character_not_found`; own character + B's `setup_id` ⇒ 404 `setup_not_found`; no session, no opening message | 011, 018 | 003 |
| 31 | GET | `/api/sessions/{}` | owner | 404 `session_not_found` | 011 | 003 |
| 32 | † | `/api/sessions/{}/archive` | owner | 404 `session_not_found` | 011 | 003 |
| 33 | † | `/api/sessions/{}/restore` | owner | 404 `session_not_found` | 011 | 003 |
| 34 | GET | `/api/sessions/{}/entries` | owner | 404 `session_not_found` | 012, 021 | 003 |
| 35 | POST | `/api/sessions/{}/entries` | owner | 404 `session_not_found` | 012 | 003 |
| 36 | GET | `/api/sessions/{}/zone` | owner | 404 `session_not_found` (zone holds tool rows too) | 013, 021 | 003 |
| 37 | POST | `/api/sessions/{}/zone/messages` | owner | 404 `session_not_found` | 013 | 003 |
| 38 | POST | `/api/sessions/{}/zone/compose` | owner | 404 `session_not_found` as JSON before any stream frame; no row written; no model call | 021 | 003 |
| 39 | POST | `/api/sessions/{}/settle` | owner | 404 `session_not_found` | 012 | 003 |
| 40 | POST | `/api/sessions/{}/reopen` | owner | 404 `session_not_found` | 012 | 003 |
| 41 | GET | `/api/sessions/{}/memo-chain` | owner | 404 `session_not_found` | 015 | 003 |
| 42 | GET | `/api/sessions/{}/configuration` | owner | 404 `session_not_found` | 017 | 003 |
| 43 | PATCH | `/api/sessions/{}/configuration` | owner | 404 `session_not_found` | 017 | 003 |
| 44 | GET | `/api/sessions/{}/export` | owner | 404 `session_not_found` | 030 | 003 |
| 45 | PATCH | `/api/messages/{}` | owner | 404 `message_not_found` | 014 | 003 |
| 46 | GET | `/api/messages/{}/discussion` | owner | 404 `message_not_found` | 022 | 003 |
| 47 | POST | `/api/messages/{}/translation` | owner | 404, code as declared by 023/003 DoD-3 | 023 | 003 |
| 48 | PATCH | `/api/memos/{}` | owner | 404 `memo_not_found` | 015 | 003 |
| 49 | DELETE | `/api/memos/{}` | owner | 404 `memo_not_found` | 015 | 003 |
| 50 | GET | `/api/characters/{}/configuration` | owner | 404 `character_not_found` | 017 | 003 |
| 51 | PATCH | `/api/characters/{}/configuration` | owner | 404 `character_not_found` | 017 | 003 |
| 52 | GET | `/api/characters/{}/export` | owner | 404 `character_not_found` | 030 | 003 |
| 53 | POST | `/api/characters/{}/import` | owner | 404 `character_not_found` | 031 | 003 |
| 54 | GET | `/api/admin/users` | admin | administrative data only | 005 | 006 |
| 55 | POST | `/api/admin/users` | admin | administrative data only | 005 | 006 |
| 56 | † | `/api/admin/users/{}/disable` | admin | administrative data only | 005 | 006 |
| 57 | † | `/api/admin/users/{}/enable` | admin | administrative data only | 005 | 006 |
| 58 | † | `/api/admin/users/{}/password` | admin | administrative data only | 005 | 006 |
| 59 | † | `/api/admin/users/{}/role` | admin | administrative data only | 005 | 006 |
| 60 | GET | `/api/admin/llm-servers` | admin | no count derived from user content | 008 | 006 |
| 61 | POST | `/api/admin/llm-servers` | admin | as row 60 | 008 | 006 |
| 62 | PATCH | `/api/admin/llm-servers/{}` | admin | as row 60 | 008 | 006 |
| 63 | DELETE | `/api/admin/llm-servers/{}` | admin | as row 60 | 008 | 006 |
| 64 | † | `/api/admin/llm-servers/{}/test` | admin | as row 60 | 008 | 006 |
| 65 | † | `/api/admin/llm-servers/{}/available-models` | admin | as row 60 | 008 | 006 |
| 66 | † | `/api/admin/llm-servers/{}/models` | admin | disabling a model B's session uses is never refused and carries no count (R5) | 008 | 006 |
| 67 | POST | `/api/admin/llm-servers/{}/embedding-model` | admin | as row 60 | 008 | 006 |
| 68 | DELETE | `/api/admin/llm-servers/{}/embedding-model` | admin | as row 60 | 008 | 006 |
| 69 | GET | `/api/admin/database/tables` | admin | schema metadata only; unchanged by content | 009 | 006 |
| 70 | POST | `/api/admin/database/tables/{}/create` | admin | schema metadata only | 009 | 006 |
| 71 | POST | `/api/admin/database/tables/{}/sync` | admin | schema metadata only | 009 | 006 |
| 72 | GET | `/api/admin/database/export` | admin | role gate only — opacity is 030's | 030 | 002 |
| 73 | POST | `/api/admin/database/import` | admin | 409 `database_not_empty` when content exists; nothing echoed, nothing wiped | 031 | 005 |
| 74 | _TBD: fast/002 plan.md_ | _TBD: vector-rebuild route(s), fast/002 plan.md_ | admin | response/progress carries no count or value derived from user content | fast/002 | 006 |

Owner-feature numbers for the built rows are the delivering plan as harvested;
they name where a `/bug-fixer` hand-back goes. Rows 5 and 74 may expand to more
than one route once fast/003 / fast/002 are planned; each expanded route takes
the row's class and outcome.

**A guard failure is a finding with two possible causes**, and the verifier
names which: a route exists that the table does not classify (an unplanned
surface → leak finding, or a table omission → `SPEC`, back to the planner to
amend this table), or the table names a route that does not exist (`SPEC`).

## Test conventions for this feature

- Backend tests are flat under `backend/tests/` (`test_<area>.py`), one module
  docstring citing the step file and DoD range, test names tagged
  `__S032_<SSS>_DoD<n>` (e.g. `__S032_003_DoD4`).
- The shared two-user world lives in **`backend/tests/privacy_audit_support.py`**
  (step 002 owns it; steps 003..007 import it as a sibling module). It is not a
  test module and is never collected.
- Existing helpers (`db_settings`, `db_engine` in `conftest.py`; the
  `_assert_envelope` / `_assert_empty_detail` pattern in router tests) are the
  precedent; the support module consolidates them rather than copying again.
- Step 007 calls the **real** `configure_logging`; every other audit step may
  no-op it as the existing router tests do.
- Frontend tests are Vitest under `frontend/tests/`, TypeScript only.
- Commands: root `CLAUDE.md` "Build & Test Commands".

## Files touched across steps

| Path | Steps |
|---|---|
| `backend/tests/privacy_audit_support.py` | written in 002; imported by 003..007 |
| `backend/app/logging.py` | changed in 001; fix-allowance in 007 |
| `backend/app/routers/`, `backend/app/services/` | fix-allowance in 003..007 (per step) |
