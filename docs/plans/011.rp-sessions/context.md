# Feature 011 — RP sessions · feature-wide context

## What this feature is

Gives the roleplayer the run itself. A **session** is started under one of the
roleplayer's characters, **with one of that character's working setups or with none**,
and no flow makes choosing a setup a precondition. A session is always resumable and
never finished. It is archived out of the working list and restored, and a restored one
reopens unchanged. Sessions appear in the tree beneath their character, ordered by last
use, with the setup shown as a label on the row and never as a tree level. One setup can
back several sessions. The session's own screen at `/sessions/:id` is, for now, an empty
screen with a header: entries, the ruler and the zone are `012` / `013`'s.

"Session" in this folder always means the **RP session** (`sessions` table). The login
session is `auth_sessions` and `services/auth.py`'s vocabulary; nothing in 011 touches it
(see Vocabulary and D11).

The agreed boundary is `brief.md` in this folder. Its Definition and Scope In/Out bound
every step and are **not** widened. Its two open questions are closed by **D3** (what
bumps `last_used_at`) and **D4** (no title).

## Product ids

`FEAT-008` via **UC-023**, **UC-024**, **UC-025**, **UC-026**; `FEAT-007` via **UC-021**,
**UC-022**; `FEAT-020` via **UC-069**.

| Criterion | Where it lands |
|---|---|
| US-026.AC-1 (start a session under a character; it is created empty) | `002`, `003` (create), `007` (start effect), `008` (Start session), `009` (the empty session screen) |
| US-027.AC-1 (archive leaves the working list) | `002`, `003`, `004` / `007` (apply-a-row removes it), `006` (gone from the tree), `008` (row action) |
| US-027.AC-2 (restore brings it back) | `002`, `003`, `004`, `007`, `008` |
| US-027.AC-3 (a restored session reopens intact) — **partially** | `002`, `003` (the restored row is field-for-field unchanged and reads by id), `009` (the screen reopens it by id). The "every entry and settled answer intact" half needs entries (`012`) |
| US-028.AC-1 (ordered by last use, most recent first) | `002`, `003` (`ORDER BY last_used_at DESC, id DESC`), `004`, `007` (insert position), `008` |
| US-029.AC-1 (only the roleplayer's own sessions) | `002`, `003` (SQL scope, R5) |
| US-024.AC-1 (start with no setup when none exists) | `002`, `003`, `007`, `008` |
| US-024.AC-3 (no flow requires choosing or creating a setup first) | `003` (setup omitted / null), `008` ("No setup" is the default; start works with an empty or failed setup list) |
| US-025.AC-1 (choose an existing setup; it is attached) | `002`, `003`, `007`, `008` |
| US-023.AC-2 (a saved setup is available to choose when starting) — 010's forward note | `007` (working setups loaded as choices), `008` (the Setup select offers them, reloaded on open, D19) |
| US-088.AC-1 (a session row shows its setup as a label) | `002` / `003` (`setup_name` joined at read time), `006` (tree), `008` (section) |
| US-088.AC-2 (no setup → nothing where the label would be) | `006`, `008` |
| US-089.AC-1 (a character's sessions in the tree by last use) | `004` (`sessionsOfCharacter` keeps server order), `006` |

UC-024 (resume) is realised as: choose a session row (tree or section) → `/sessions/:id`
reads it with `GET /api/sessions/{session_id}` (`006`, `009`). UC-022 is proved by two
sessions sharing one setup (`002`, `003`). R2 (no sentinel setup at session start), R5,
R6 are cited on the DoD items that prove them.

**Not delivered here, recorded as forward notes, never faked with stand-in tests:**

- **US-024.AC-2** (adding entries and composing with no setup works) — `012` / `021`.
- **US-025.AC-2** (memo chain and search anchor resolve independently per session) —
  `015` / `026` / `027`.
- **US-027.AC-3's "every entry and settled answer intact"** — 011 proves the restored row
  is unchanged and reopens by id; the entries half arrives with `012`.
- **US-117 / UC-080** (start a session by writing on the character page) — `018`
  (brief Out).
- **US-021.AC-2** (a later session uses the updated persona) — `020`.
- **R4 model capture at creation** — `017` (brief Out). 011's sessions carry **no
  `model_ref`**. Sessions created before `017` will need `017` to decide their
  `model_ref` (backfill, or null until first resolution). `outcome.md` records it; 011
  decides nothing about it.

## Build prerequisite — 008, 009, 010 are planned, not built

001..007 are built. **008 is at skeleton stage** in the working tree (stub bodies, not
coded). **009 and 010 are planned, not built.** 011 binds to their **planned** contracts,
cited from their step files and not re-specified.

| Upstream artifact | What 011 relies on | Needed by |
|---|---|---|
| `backend/app/db/schema.py` `characters` (009 `001`) and `setups` (010 `001`) Tables | the FK targets of `sessions.character_id` / `sessions.setup_id`; the scoped parent and setup selects | `001`, `002` |
| `backend/app/errors.py` `CharacterNotFoundError` (009 `001`), `SetupNotFoundError` (010 `001`) | raised by 011 for a missing/foreign parent character and for a setup that is not the caller's under that character | `002`, `003` |
| `backend/app/models/characters.py` / `models/setups.py` (009 / 010 `001`) | the model pattern (`SnowflakeOut`, `extra="ignore"`) | `001` (pattern only) |
| `backend/app/services/characters.py` / `services/setups.py` (009 / 010 `002`) | the service pattern (009 `002.context.md` "Service conventions"; 010 D6). **Not imported** (D11) | `002` (pattern only) |
| `backend/app/routers/characters.py`, `routers/setups.py` + their `main.py` registration (009 / 010 `003`) | 011's router is registered **after** setups; router tests create characters and setups through 009's and 010's routes, and archive a setup through 010's | `003` |
| `frontend/src/app/charactersApi.ts` / `charactersState.ts` (009 `004`) | `Character`, `isArchived`, `CharactersState` (`characters`, `status`, `showArchived`) | `006`, `009` |
| `frontend/src/app/setupsApi.ts` (010 `004`) | `Setup`, `fetchSetups(characterId, includeArchived, signal?)` | `007` |
| `frontend/src/app/CharacterTree.tsx` (009 `008`) | header (Search, New character, Show archived), "Characters" list, row links, active mark, reload effect. **Edited by `006`** | `006` |
| `frontend/src/app/WorkspaceShell.tsx` (008 `004`, + 009 `008`'s `characters` prop) | expanded column renders the tree; has `storage`. **Edited by `006`** | `006` |
| `frontend/src/app/App.tsx` (008 `004`, 009 `007` / `008`) | six routes, one `CharactersState` via `useState`, `user` / `storage` props; `/sessions/:id` an empty centre. **Edited by `006`, `008`, `009`** | `006`, `008`, `009` |
| `frontend/src/app/CharacterScreen.tsx` (009 `007`, 010 `006`) | existing-mode "ready" render: persona block, `SetupsSection`, then the empty "Sessions" heading; `CharacterRoute` keyed by id. **Edited by `008`** | `008` |
| `frontend/src/app/workspaceLayout.ts` (008 `001`) | the `LayoutStorage` type only (the collapse module takes the same storage) | `005`, `006` |
| 008 / 009 / 010 tests (`App.test.tsx`, `WorkspaceShell.test.tsx`, `CharacterTree.test.tsx`, `CharacterScreen.test.tsx`, `AppBoot.test.tsx`, `entries.test.tsx`) | amended where 011 changes what they observe; each amendment is named in the owning step's context | `006`, `008`, `009` |

- **Steps `001`–`003` (backend)** need 009 `001`–`003` and 010 `001`–`003` delivered.
- **Step `004`** imports only `shared/` modules and needs nothing upstream (its character
  ordering reads only an `id` string; `004.context.md`). It may be built before 009.
- **Step `005`** imports only the `LayoutStorage` type from 008 `001`.
- **Step `006`** edits `CharacterTree.tsx`, `WorkspaceShell.tsx`, `App.tsx` and amends
  008/009 tests: needs **008 and 009 delivered**.
- **Step `007`** imports 010's `setupsApi.ts`: needs **010 `004` delivered**.
- **Step `008`** edits `CharacterScreen.tsx` after 010's section placement: needs **008,
  009 and 010 delivered**.
- **Step `009`** edits `App.tsx`: needs **008 and 009 delivered**.

## Built state this feature reads (001..007 are built)

Exactly as 009's `context.md` "Built state this feature reads" lists it (`errors.py`
`DomainError`, `models/ids.py` `SnowflakeOut` / `SnowflakeIn`, `ids.py`
`SnowflakeGenerator`, `routers/bootstrap.py` `get_id_generator`, `dependencies.py`
`require_user` → `CurrentUser`, `db/engine.py` `get_connection`, `main.py`; frontend
`shared/api.ts`, `shared/apiError.ts`, `shared/IconButton.tsx`, `shared/AppProviders.tsx`,
the MobX precedents). Plus `backend/app/services/auth.py`, read only for its names, which
011 must not shadow (D11).

## Wire contract — sessions

`routers/sessions.py`, router-level `require_user`, full paths for two families (D9).

| Route | Body | Answers |
|---|---|---|
| `GET /api/sessions` | — | 200 `{ sessions: [Session…] }`: the caller's **working** sessions across all characters. `?include_archived=true` adds archived ones. Order: D14. Feeds the tree |
| `GET /api/characters/{character_id}/sessions` | — | 200 `{ sessions: [Session…] }`: that character's working sessions; `?include_archived=true` adds archived. Order: D14. The character must be the caller's (archived or not). Feeds the section |
| `POST /api/characters/{character_id}/sessions` | omitted, `{}`, or `{ setup_id: string \| null }` | **201** the created `Session` (D2). The character must be the caller's; an archived character is allowed |
| `GET /api/sessions/{session_id}` | — | 200 the `Session`, archived or not, whatever its character's archive state. **Reads only** (D3) |
| `POST /api/sessions/{session_id}/archive` | — | 200 the `Session` (idempotent, D13) |
| `POST /api/sessions/{session_id}/restore` | — | 200 the `Session` (idempotent, D13) |
| any `PATCH` or `DELETE` on either family | — | **405**. Nothing is editable in 011; no delete route exists (R6) |

`Session` on the wire:

```
{ id: "<decimal string>", character_id: "<decimal string>",
  setup_id: "<decimal string>" | null, setup_name: string | null,
  archived_at: string | null, last_used_at: string,
  created_at: string, updated_at: string }
```

Timestamps are `data-model.md`'s fixed-width form (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`).
`user_id` is **never** on the wire. `setup_name` is the setup's current name, joined at
read time, and present **even when that setup is archived** (D10).

Failures:

- `character_id` that addresses no row **or another user's character** → **404
  `character_not_found`** (009's code), empty `detail`;
- `setup_id` that addresses no setup **of the caller under that same character** →
  **404 `setup_not_found`** (010's code), empty `detail`;
- `setup_id` addressing the caller's setup under that character that is **archived** →
  **409 `setup_archived`** (new, D12), empty `detail`;
- `session_id` that addresses no row **or another user's session** → **404
  `session_not_found`** (new, D12), empty `detail`;
- a non-numeric path id or `setup_id` → 422; no login session → 401 `not_authenticated`.

## Commands

From the root `CLAUDE.md`:

```
Backend  (run from backend/)
  test       .venv/Scripts/python -m pytest
  typecheck  .venv/Scripts/python -m mypy app
  lint       .venv/Scripts/python -m ruff check .
Frontend (run from frontend/)
  build      npm run build
  test       npm test
  typecheck  npm run typecheck
```

No backend step may leave `mypy app` or `ruff check .` failing. No frontend step may leave
`npm run typecheck` failing.

## Architecture this binds to

- `docs/architecture/data-model.md`: **`sessions`** (column list, no status column,
  `last_used_at` versus `updated_at`, the `model_ref` capture paragraphs — deferred, D8),
  the **timestamp convention**, **Identifiers**, "Roleplay content" (direct `user_id`),
  **"… and the archive rule"** (no cascade), "FTS5 tables" (`session_fts` indexes `title`,
  `partner_label` — not declared here, D4), "Schema drift and rebuild" (`Create`).
- `docs/architecture/domain-rules.md`: **R2** (nullable `setup_id`, no default, no
  sentinel; no flow requires a setup), **R4** (model capture — deferred to `017`), **R5**,
  **R6** in full.
- `docs/architecture/backend-structure.md`: "Layout" (`routers/sessions.py`,
  `services/sessions.py`), "Routers versus services", "Authorization as router
  dependencies", "The JSON id boundary", the stream route table's
  `POST /api/characters/{character_id}/sessions` row and its two bullets (011 ships the
  no-message form, D2), "The error model", "The per-code status record".
- `docs/architecture/frontend-structure.md`: "State — MobX 6", "Where a store's file
  lives", **"Routing inside the `app` entry"** (the archive-toggle `_TBD:`, which D5 closes
  for sessions; "`/characters/:id` also starts sessions"), "Ids are strings", "The API
  client".
- `docs/architecture/workspace-shell.md`: **"The three columns"** (two-level tree, setup as
  a label, newest use first), "Layout persistence" (the posture the collapse module copies,
  D7), "The character page" and its composer `_TBD:` (stays `018`'s, D1).
- `docs/architecture/ui-conventions.md`: `IconButton`, the **icon table** (`IconPlus`,
  `IconArchive` / `IconArchiveOff`, `IconDots`, "Expand / collapse a character in the tree:
  `IconChevronDown`, rotated `-90°` when collapsed", and the "One chevron, rotated" note),
  **Tables** (one overflow `Menu` per row), "Loading, errors and empty states", **"Async
  feedback"**, **"Mutations are never optimistic"**, the confirm convention ("Deliberately
  NOT confirmed").
- `docs/product/use-cases/FEAT-008.rp-sessions.md`, `docs/product/stories/FEAT-008.rp-sessions.md`,
  `use-cases/FEAT-007.setups.md`, `stories/FEAT-007.setups.md`,
  `use-cases/FEAT-020.workspace-shell.md`, `stories/FEAT-020.workspace-shell.md`.

Cited, never copied.

## Files this feature touches

```
backend/
  app/db/schema.py                 # + sessions Table literal                          (001)
  app/errors.py                    # + SessionNotFoundError, SetupArchivedError        (001)
  app/models/sessions.py           # NEW — 3 pydantic models                           (001)
  app/services/sessions.py         # NEW — RpSession value + 6 operations              (002)
  app/routers/sessions.py          # NEW — /api/sessions, /api/characters/{id}/sessions (003)
  app/main.py                      # registers the sessions router after setups        (003)
  tests/test_db_schema.py (011 delta), tests/test_sessions_models.py,
  tests/test_admin_db_router.py (checked; conditional)                                 (001)
  tests/test_sessions_service.py                                                       (002)
  tests/test_sessions_router.py                                                        (003)
frontend/
  src/app/sessionsApi.ts           # NEW — Session type + 6 calls                      (004)
  src/app/sessionsState.ts         # NEW — workspace sessions data class + fns         (004)
  src/app/sessionLabel.ts          # NEW — start-time label formatter (pure)           (005)
  src/app/treeCollapse.ts          # NEW — collapsed-characters record (pure)          (005)
  src/app/CharacterTree.tsx        # session level, chevron, ordering                  (006)
  src/app/WorkspaceShell.tsx       # passes sessions + storage to the tree             (006)
  src/app/App.tsx                  # SessionsState; props to screens; /sessions/:id    (006, 008, 009)
  src/app/sessionsSectionState.ts  # NEW — section data class + fns                    (007)
  src/app/SessionsSection.tsx      # NEW — the section on the character screen         (008)
  src/app/CharacterScreen.tsx      # renders the section in place of the heading       (008)
  src/app/sessionScreenState.ts    # NEW — session screen data class + load            (009)
  src/app/SessionScreen.tsx        # NEW — the session's own screen + route wrapper    (009)
  tests/app/sessionsApi.test.ts, tests/app/sessionsState.test.ts                       (004)
  tests/app/sessionLabel.test.ts, tests/app/treeCollapse.test.ts                       (005)
  tests/app/CharacterTree.test.tsx, tests/app/WorkspaceShell.test.tsx,
  tests/app/App.test.tsx, tests/app/AppBoot.test.tsx, tests/entries.test.tsx           (006)
  tests/app/sessionsSectionState.test.ts                                               (007)
  tests/app/SessionsSection.test.tsx, tests/app/CharacterScreen.test.tsx,
  tests/app/App.test.tsx                                                               (008)
  tests/app/sessionScreenState.test.ts, tests/app/SessionScreen.test.tsx,
  tests/app/App.test.tsx, tests/entries.test.tsx                                       (009)
```

**Not touched. A step that touches one is out of scope:** every 009 / 010 backend module
(`models/`, `services/`, `routers/` for characters and setups), `backend/app/services/auth.py`,
`backend/app/dependencies.py`, `backend/app/ids.py`, `backend/app/models/ids.py`,
`backend/app/db/engine.py`, `backend/app/db/drift.py`, `backend/app/db/sync.py`, every
other router and service, `backend/tests/conftest.py` (no shared fixtures), 009's and
010's backend tests, `backend/tests/test_llm_registry_models.py` and
`backend/tests/test_llm_registry_servers.py` (their `{"sessions", "characters", "memos"}`
string set is unaffected by registering `sessions`; checked, no action). Frontend:
`src/app/charactersApi.ts`, `charactersState.ts`, `characterScreenState.ts`,
`setupsApi.ts`, `setupsSectionState.ts`, `SetupsSection.tsx`, `SetupModal.tsx`,
`setupDraft.ts`, `workspaceLayout.ts`, `shellState.ts`, `UserMenu.tsx`, `AppBoot.tsx`,
`main.tsx`, `src/shared/*`, `src/admin/*`, `src/shell.css`, `src/global.css`,
`frontend/package.json` and the lockfile (**no new npm dependency**), `vite.config.ts`,
`tests/conventions.test.ts`, `tests/ids-are-strings.test.ts`, `tests/setup.ts`, 010's
`SetupsSection.test.tsx` / `setupsSectionState.test.ts`.

## Cross-cutting constraints every step holds

**Owner scope lives in SQL.** Every statement that reads or writes `sessions` carries
`sessions.user_id = <caller's id>` in its own `WHERE` (or `VALUES` for the insert). The
parent check carries `characters.user_id`, the setup check carries `setups.user_id` (and
`setups.character_id`), and the `setup_name` join carries `setups.user_id`, each in its own
predicate. Nothing is fetched and filtered in Python; nothing in the frontend filters by
owner (R5). The service takes `user_id` as a **required positional** argument.

**Routers own HTTP; services own SQL.** No SQL in `routers/sessions.py`; no `fastapi`
import in `services/sessions.py`; `models/sessions.py` imports neither. **Services do not
call each other** (D11).

**No delete path, anywhere.** No `DELETE` route, no delete function, no `DELETE`
statement against `sessions`, no frontend call that deletes (R6).

**No default setup, no sentinel, anywhere.** A session with no setup has `setup_id` NULL.
Nothing creates a setup, and no "(none)" row exists or is invented (R2). The frontend's
"No setup" choice maps to `null` and never reaches the wire as anything else.

**No model capture.** Nothing in 011 resolves, writes or reads a model reference (R4 is
`017`'s).

**Ids are strings in every frontend file and every JSON payload.** `Session.id`,
`character_id` and `setup_id` are `string` (or `null`). No `parseInt`, no `id: number`, no
ordering derived from an id: client-side ordering uses fixed-width `last_used_at` text
only. The backend converts only through `SnowflakeOut` / `SnowflakeIn`.

**No context, no methods.** As 009 `context.md` states it (data classes with observable
fields only, free functions that `runInAction`, abort-aware, never reject; `useState`
instances passed as props; `observer` on every reader).

**Never optimistic.** A mutation renders only the server's returned row (D15).

**Every icon-only control goes through `shared/IconButton`.** Tests find controls by
accessible name. The names fixed in the step files are the contract.

**TypeScript only.** No `.js` / `.jsx` / `.mjs` / `.cjs`.

## Decisions — settled, with their reasoning

"009 Dn" are in `docs/plans/009.characters/context.md`; "010 Dn" in
`docs/plans/010.setups/context.md`.

### D1 — Starting a session is inline in the character screen's Sessions section (user decision)

009's empty "Sessions" section on `/characters/:id` (existing mode, `"ready"`; absent in
new mode and non-ready states) becomes a real section (`008`). It holds an inline Mantine
`Select` labelled **"Setup"** whose first and default option is **"No setup"**, followed by
the character's **working** setups (`fetchSetups(characterId, false)`; archived setups are
never offered, per 010 D3's forward note), and a labelled button **"Start session"**
(`IconPlus` left section). No modal: a one-choice control is not a form, and the start is
one click from the place the roleplayer already is.

On success the returned row is applied to both states (D15) and the client navigates
in-entry to `/sessions/<id>` with the id string exactly as received. It is a **push**, not
a `replace`: unlike 009 D1's empty create form, the character page stays a valid place to
come Back to. If the setup list fails to load or is empty, "No setup" still starts a
session (US-024.AC-3, R2).

The character page's composer (UC-080, US-117) and its `_TBD:` in `workspace-shell.md`
stay `018`'s; `018` may rebuild this section.

### D2 — The create route ships without an opening message (user decision)

`POST /api/characters/{character_id}/sessions`, body omitted, `{}`, or
`{ setup_id: string | null }`; 201 the created session, empty of entries. Owned by
`routers/sessions.py` as `backend-structure.md` already says. `018` later extends **this
same route and transaction** with an optional opening message (UC-080). 011 ships the
no-message form only. `outcome.md` amends the route table row and bullets.

- An **archived character** is allowed (as 010 D5: nothing forbids it, and archive does
  not cascade).
- A supplied `setup_id` must address a setup **of the caller under that same character**,
  checked inside the create transaction; otherwise 404 `setup_not_found`.
- An **archived** setup is refused with 409 `setup_archived` (D12): it is never offered,
  so a request naming one is stale or hand-made.
- Omitted or `null` `setup_id` → a session with none. Unknown body keys are ignored
  (`character_id`, `user_id`, `last_used_at`, `title` cannot be set through a body).

### D3 — `last_used_at` is set at creation and bumped only by content writes (user decision; closes brief open question 1)

At creation `last_used_at` = `created_at` = `updated_at` (one instant). It is bumped
**only by content writes**, and none exists before `012` (forward note: append, settle and
compose bump it). **Opening or reading never bumps it; archive and restore never bump it.**
So in 011 the last-use order **equals creation order**, which the tests may rely on.

There is **no resume or touch route**: "resume" is `GET /api/sessions/{session_id}`, a
pure read, archived or not. Reasoning: a read that writes would turn every navigation into
a write on SQLite's single writer (the same argument as `backend-structure.md`'s "no
sliding session expiry"), and "last use" in UC-026 means working, not glancing.

### D4 — No title in 011 (user decision; closes brief open question 2)

`title` and `partner_label` are **not declared**. No product id lets the roleplayer set
either, and a column with no writer would be a stored empty string forever. The feature
that lets the roleplayer label a session adds the column; `session_fts` lands with
FEAT-017's plan, which needs whatever text exists by then.

A session row and the session header show its **start time** as the label, from
`created_at`, through one pure formatter (`005`): **`YYYY-MM-DD HH:MM`**, 24-hour,
zero-padded, in the browser's local time zone. The formatter takes an optional IANA time
zone so its unit tests pin exact values; components call it without one. Component tests
assert only the label's fixed shape (Test conventions).

### D5 — Archived sessions surface only on the character screen (user decision; closes `frontend-structure.md`'s archive-toggle `_TBD:` for sessions, and so entirely)

- The Sessions section header carries a Mantine `Switch` labelled **"Show archived
  sessions"**: off by default, **not persisted** (009 D4 / 010 D4 reasoning). Its label is
  distinct because "Show archived" (tree) and "Show archived setups" (010) are on the same
  page.
- Section rows: each is a router link to `/sessions/<id>` showing the start-time label
  and the setup label (or nothing). Archived rows are **dimmed** with an **"Archived"**
  badge. **Archive / Restore are row actions** in one overflow `Menu` behind one
  `IconButton` (`IconDots`) labelled **"Actions for <start-time label>"**, items
  **"Archive"** (`IconArchive`) or **"Restore"** (`IconArchiveOff`). No confirm
  (non-destructive; `ui-conventions.md` "Deliberately NOT confirmed").
- **The tree never shows archived sessions** (it loads only the working list).
- `/sessions/<id>` opened directly on an archived session (reachable by URL; 009's forward
  note, R6) shows an **"Archived"** badge and **no archive controls**.

### D6 — Characters in the tree are ordered by newest session use (user decision)

A character sorts by the **maximum `last_used_at`** among its sessions in the workspace
sessions state, most recent first. Characters with no sessions follow, in the characters
state's own order (009 D10: `created_at DESC`). Ties keep the characters state's order.
Derived **client-side by one pure function** (`004`) from the two loaded lists, compared
as fixed-width text, never by id. 009's backend order is untouched. This replaces 009
D10's interim tree order (009's forward note).

### D7 — Per-character chevron, expanded by default, collapse persisted under its own key (user decision; storage key is an orchestrator refinement; glyph and absence refined here)

- Every character **that has at least one session in the tree** carries a chevron
  `IconButton` before its link, `sizeVariant` "chevron", labelled **"Collapse <name>"**
  while expanded and **"Expand <name>"** while collapsed. A character with no sessions has
  **no chevron**: a control for an action that does not currently exist is absent, not
  inert (`ui-conventions.md`'s `IconArrowBackUp` and discard precedents). Planner
  refinement; flagged in the hand-back.
- The glyph is **`IconChevronDown`, rotated `-90°` when collapsed** (`ui-conventions.md`
  icon table, "Expand / collapse a character in the tree", and the "One chevron, rotated,
  not two icons" note, which supersedes a Down/Right pair). The rotation is done by the
  icon component handed to `IconButton` (a small local wrapper), not by widening
  `IconButton`'s props.
- Expanded is the default. The collapsed set persists in localStorage under the **separate
  key `"rphelper.tree-collapsed"`**, a JSON array of collapsed character id strings, read
  and written by its own small module (`005`) with 008's `workspaceLayout.ts` posture
  (takes a `LayoutStorage | null`, total read, best-effort write, never throws, DOM- /
  React- / MobX-free). **Not** a field in 008's workspace-layout record: 008's reader drops
  unknown keys by design and its tests pin that (008 `001` DoD-8, DoD-11).
- The collapsed set is **component-local view state** in the tree (`useState` initialised
  from the record), like `ui-conventions.md`'s modal flags: nothing else reads it.

### D8 — The `sessions` table (orchestrator decision)

Eight columns: `id` (snowflake PK), `user_id` (FK `users.id`, NOT NULL), `character_id`
(FK `characters.id`, NOT NULL), `setup_id` (FK `setups.id`, **nullable, no server
default, no sentinel**), `last_used_at`, `archived_at` (nullable), `created_at`,
`updated_at` (Text, fixed-width). **No `ON DELETE`** (no delete path exists). **No status
column** (`data-model.md`).

**Deferred:** `title`, `partner_label` (D4); `rp_language`, `preferred_language`,
`model_ref`, `system_prompt`, `tools` (`017`, whose plan fixes `model_ref`'s encoding,
still `_TBD:` in `data-model.md`).

**One composite non-unique index on `(user_id, character_id)`**, as 010 D7: the
per-character list filters both columns, and the leftmost `user_id` prefix serves the
all-sessions list and every by-owner scan. The `last_used_at` sort runs over one user's
rows, a small set; a second index would be one more structure to keep in sync for no
measurable gain. No index on `setup_id`: no query filters by it (010 D3 keeps reverse
counts out).

No DDL at startup. A fresh instance gets the table from bootstrap's `create_all`; an
existing one reports `sessions` as **missing** (and `/api/health` `schema: "missing"`)
until an administrator presses **Create** (FEAT-005).

### D9 — The route surface (orchestrator decision)

The Wire contract table. One router (routers group by feature), router-level
`require_user`, full paths for both families, registered in `main.py` **after** the setups
router. The child collection hangs off the character (created under it, listed for it);
single-session routes are flat (a session id is globally unique). `GET /api/sessions`
takes `include_archived` too, per R6's explicit-flag rule, although the tree never sets
it. Archive / restore are named action routes (009 D7). No `PATCH`: nothing is editable.

### D10 — `Session` carries `setup_name`, joined at read time (orchestrator decision)

`setup_name` is the referenced setup's current `name`, by an owner-scoped LEFT JOIN, in
every read and in the create/archive/restore responses. It is shown **even when that setup
is archived**: archive does not cascade (010 D3), and an existing session keeps its label.
A join, not a copied column, so a renamed setup relabels its sessions with no fan-out
write. This is what lets the tree and the section show US-088's label without a second
request.

### D11 — Service naming and isolation (orchestrator decision, names chosen here)

The RP modules keep the architecture's names (`routers/sessions.py`,
`services/sessions.py`, `models/sessions.py`). Inside them, names must not read as the
login session (`services/auth.py` owns `OpenedSession`, `open_session`,
`resolve_session`, `revoke_session`, `revoke_user_sessions`):

- value object **`RpSession`**;
- operations **`start_session`**, **`list_sessions`** (all characters),
  **`list_character_sessions`**, **`get_session`**, **`archive_session`**,
  **`restore_session`**;
- errors **`SessionNotFoundError`**, **`SetupArchivedError`**.

`services/sessions.py` checks the parent character and the chosen setup with **its own
owner-scoped selects inside the same transaction** and never imports another service
(010 D6's reasoning: a service operation owns its transaction).

### D12 — Not-found, conflict and validation (orchestrator decision)

- `session_not_found` (404, empty `detail`) answers "no such session" and "another user's
  session" indistinguishably (R5). A new `DomainError` subclass shaped like 009's.
- A missing/foreign parent on list or create answers `character_not_found`; a setup that
  is not the caller's **under that character** (nobody's, another user's, or one of the
  caller's other characters') answers `setup_not_found`. Each code names what the request
  addressed; no new code for the same condition.
- **`setup_archived` → 409**, empty `detail`: the request is well formed and the caller
  owns the setup, but its state conflicts with the operation (the same shape as
  `username_taken` / `self_role_change_refused`). Not 404: the setup exists for this
  caller, and saying otherwise would be false. Not 422: no field is malformed.
- Check order inside the create transaction: character, then setup existence, then setup
  archive state.

### D13 — Archive semantics (orchestrator decision; as 009 D9)

Archive sets `archived_at`; on an archived session it is a **no-op keeping the original
`archived_at`**. Restore sets NULL; on a working one it is a no-op. A state change bumps
`updated_at` and **never `last_used_at`** (D3); a no-op writes nothing. Archiving a
session's character or setup changes nothing on the session.

### D14 — Order: `last_used_at DESC, id DESC` (orchestrator decision)

Both lists. The snowflake breaks a same-microsecond tie server-side; the client never
orders by id (it inserts by `last_used_at` text alone, D15).

### D15 — One workspace sessions state plus a section-owned state (orchestrator decision)

- **`SessionsState`** (`004`): the caller's **working** sessions across all characters,
  for the tree. Created **once** in `App` with `useState` and passed as props, like 009
  D11's `CharactersState`. Its pure upsert **`applySession`**: an archived row is removed
  (it is never shown in the tree); a working row is removed if present and inserted at its
  `last_used_at`-descending position. Unchanged `last_used_at` therefore keeps its index.
- **`SessionsSectionState`** (`007`): one character's list (with the archived switch), the
  setup choices, the selection, start/row-action status and errors; created by the section
  with `useState`, the section rendered **keyed by the character id** (010 D11 precedent).
- The section's start, archive and restore **apply the returned row to both** states, so
  the tree updates with no refetch and no refetch racing the mutation. Never optimistic in
  009 D11's narrowed form: what renders is what the server returned.

### D16 — The tree's session level (orchestrator decision; label form chosen here)

009's `CharacterTree` gains: D6's character order; D7's chevron; under an expanded
character, its working sessions in last-use order (US-089), each a router link to
`/sessions/<id>` showing the start-time label and, when the session has one, the setup
label as **dimmed small text** beside it (not a `Badge`: badges on this tree already mean
state, "Archived", and a label is not a state), or nothing at all (US-088.AC-2).
`aria-current="page"` on the session row of the active `/sessions/:id`. Sessions of an
archived character appear under it only when "Show archived" shows that character. The
tree loads `SessionsState` on mount (working list only, not reloaded by the "Show
archived" switch). A sessions load failure renders inline in the tree with Retry; the
character level still renders.

### D17 — The session's own screen (orchestrator decision; fallback chosen here)

`/sessions/:id` (replacing 008's empty centre) renders `SessionScreen`, keyed by id:
loading → `Loader`; `session_not_found` → **"Session not found"**; other failure →
**"Could not load the session"** with **"Retry"**; ready → a header with a link to
`/characters/<character_id>` whose text is the character's name **from `CharactersState`
when it holds that character, else the neutral text "Character"** (no extra fetch: the
link works either way, and a second request for a label is not worth its failure mode),
a heading with the start-time label, the setup label or nothing, an **"Archived"** badge
when archived, and the line **"No entries yet."**. No archive controls (D5), no stream,
ruler, composer or zone (`012` / `013`), no wall (`015` / `016`).

### D18 — Feedback: every 011 failure has a place of its own (as 009 D12 / 010 D12)

Fixed sentences per action: **"Could not start the session."**, **"Could not archive the
session."**, **"Could not restore the session."** (inline `Alert` in the Sessions
section); **"Could not load sessions"** + **"Retry"** (section, and tree); **"Could not
load the session"** + **"Retry"** (session screen). A failed load of the setup choices
renders the dimmed line **"Could not load setups to choose from."** under the Select, with
no retry and no effect on starting (planner addition: a silent failure would hide why the
list holds only "No setup"). 011 adds **no `notifyFailure` call site** and no success
feedback beyond the re-rendered row or the navigation.

### D19 — The setup choices reload each time the Select opens (planner decision)

The section loads its setup choices on mount **and again whenever the Select's dropdown
opens**. Without it, a setup created in 010's Setups section on the same page would not be
choosable until a remount: exactly the US-023.AC-2 flow ("saved, then available to choose
when starting"). One small GET per open is cheap; the existing selection is kept.

### D20 — Nine steps

Backend in three (table + errors + models; service; router), as 009 D14 / 010 D14 split
them. Frontend in six: the API client with the workspace state; the two pure tree-display
modules (label formatter, collapse record), split out so the tree step stays under budget;
the tree; the section's state; the section with its hook into the character screen; the
session screen with its route. The suggested eight became nine because the section's state
plus component plus screen hook would exceed 200 LoC in one step.

## Test landmines (harvester-confirmed)

- `backend/tests/test_admin_db_router.py`'s `UNDECLARED_NAMES`: 010 `001` DoD-9 leaves it
  holding a name **no planned feature will declare**, so registering `sessions` needs no
  swap. `001` carries a conditional DoD in case the list still names `sessions`.
- `backend/tests/test_db_schema.py` holds 006's, 009's and 010's registry deltas in the
  later-table-proof form (009 `001` DoD-11, 010 `001` DoD-1 / DoD-8). 011 adds its own the
  same way and keeps the earlier ones passing.
- `test_llm_registry_models.py:~595` and `test_llm_registry_servers.py:~813` hardcode
  `{"sessions", "characters", "memos"}` as a plain string set; registering `sessions` does
  not affect them. No action.
- Frontend: every `fetch` stub in 008/009/010 tests that renders `App` or the tree now also
  sees `GET /api/sessions`; the character screen now also requests
  `GET /api/characters/<id>/sessions` and a **second** `GET /api/characters/<id>/setups`
  (the Select's choices). Each owning step's context names the amendment.

## Vocabulary

| Term | Means here |
|---|---|
| **session** | one `sessions` row: an RP run under one character, owned by one user. Never the login session |
| **login session** | an `auth_sessions` row (`services/auth.py`); not touched by 011 |
| **working list** | sessions with `archived_at IS NULL` |
| **archived** | `archived_at` set; out of the working lists and the tree, still readable by id and with `include_archived=true` |
| **last use** | `last_used_at`; equals creation time until `012`'s content writes bump it (D3) |
| **start-time label** | `created_at` formatted `YYYY-MM-DD HH:MM` in local time (D4) |
| **setup label** | `setup_name` beside a session's start-time label; nothing when `setup_id` is null |
| **the workspace sessions state** | the one `SessionsState` `App` creates (D15) |
| **the section** / **section state** | the "Sessions" region on the character screen and its one `SessionsSectionState` (D1, D15) |
| **the session screen** | the centre column at `/sessions/:id` (D17) |
| **collapsed set** | the character ids whose session rows the tree hides, persisted under `rphelper.tree-collapsed` (D7) |
| **apply a row** | upsert a server-returned `Session` by D15's rule (workspace) or the section's rule (`007`) |
| **Archived badge** | a Mantine `Badge` reading exactly "Archived" |

## Step map

| Step | Subject | Est. LoC | Depends on |
|------|---------|----------|------------|
| 001 | `sessions` Table, `SessionNotFoundError`, `SetupArchivedError`, `models/sessions.py` | ~95 | 009 `001`, 010 `001` delivered |
| 002 | `services/sessions.py` — `RpSession` + six operations | ~175 | 001; 009 / 010 `001` delivered |
| 003 | `routers/sessions.py` + `main.py` registration | ~95 | 001, 002; 009 / 010 `001`–`003` delivered |
| 004 | `app/sessionsApi.ts` + `app/sessionsState.ts` | ~145 | 003 (wire contract) |
| 005 | `app/sessionLabel.ts` + `app/treeCollapse.ts` | ~80 | 008 `001` (type only) |
| 006 | `CharacterTree.tsx` session level + chevron + order; `WorkspaceShell.tsx`; `App.tsx` | ~140 | 004, 005; 008 + 009 delivered |
| 007 | `app/sessionsSectionState.ts` | ~140 | 004; 010 `004` delivered |
| 008 | `app/SessionsSection.tsx` + `CharacterScreen.tsx` hook + `App.tsx` props | ~150 | 004, 005, 006, 007; 008 + 009 + 010 delivered |
| 009 | `app/sessionScreenState.ts` + `app/SessionScreen.tsx` + `/sessions/:id` in `App.tsx` | ~120 | 004, 005, 006; 008 + 009 delivered |

## Test conventions

**Inherited verbatim from 009 `context.md` "Test conventions"**: the backend paragraph
(pytest from `backend/`, no shared fixtures added, schema from `create_all`, per-file
`application` / `client` fixtures with a file-local `_insert_user` and `_login`, two users
for isolation), the frontend paragraph (Vitest, `globals: false`, `tests/` mirrors `src/`,
each `it` title ends **`— DoD-N`** of its own step, `fetch` stubbed per test with
`vi.stubGlobal`, `AppProviders`, `MemoryRouter` where routed, assertions on rendered
behaviour only), and the **`vi.mock` stub of `src/shared/MarkdownEditor`**. Plus 010's
additions (the FK chain, Mantine portals, scoping to the "Setups" region).

Additions for 011:

- **FK chain.** A `sessions` row needs its user and character rows, and its setup row when
  `setup_id` is set. Service tests raw-insert characters and setups into their Tables (and
  may raw-insert sessions with chosen `last_used_at` values to prove the order is by last
  use and not by creation). Router tests create characters and setups through 009's and
  010's routes and archive a setup through `POST /api/setups/{id}/archive`.
- **Stubs routed by exact path.** `/api/sessions`, `/api/sessions/<id>`,
  `/api/characters/<id>/sessions`, `/api/characters/<id>/setups` and `/api/characters`
  share prefixes. A stub or request counter must key on the exact pathname plus query
  string, never on a prefix.
- **Start-time labels.** Exact label values are asserted **only** in `005`'s formatter
  tests, which pass an explicit time zone. Component tests identify session rows by their
  link `href` (`/sessions/<id>`) and by the setup label, and assert a start-time label only
  by its fixed shape (`/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/`), never by an exact local-time
  string and never by calling the formatter to compute an expectation.
- **Mantine `Select`.** Its options render in a portal: open it by clicking the combobox
  labelled "Setup" and choose with `screen.getByRole("option", { name })`.
- **Scoping.** The section is a region named **"Sessions"**; the screen also carries 010's
  "Setups" region, the character's own "Archived" badge, and (in `App`) the tree's
  switches and badges. Section assertions use `within(getByRole("region", { name:
  "Sessions" }))`; tree assertions scope to the "Workspace navigation" nav or the
  "Characters" list; session-screen assertions scope to the main region.
