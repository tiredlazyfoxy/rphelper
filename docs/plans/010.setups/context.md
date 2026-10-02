# Feature 010 — Setups · feature-wide context

## What this feature is

Gives a character reusable descriptions of a situation that several sessions can later
share. A setup is a **name plus one markdown `description`**, created under one of the
roleplayer's characters. It is listed in a **"Setups" section on 009's character screen**
(`/characters/:id`), created and edited in a Mantine `Modal`, archived out of the working
list and restored, and never destroyed. Every query is scoped to the owner in SQL, and
another user's setup or character answers 404. The setup is **genuinely optional**: this
feature adds the object and its lifecycle and **no flow that requires one**. Choosing a
setup when starting a session is `011`'s.

The agreed boundary is `brief.md` in this folder. Its Definition and Scope In/Out bound
every step and are **not** widened. Its one open question (archiving a setup that sessions
reference) is closed by **D3**.

## Product ids

`FEAT-007`, via **UC-020** and **UC-068**.

| Criterion | Where it lands |
|---|---|
| US-023.AC-1 (create under a character saves it) | `002` (service), `003` (route), `005` (the modal's submit), `006` (the section shows the created row) |
| US-087.AC-1 (archive leaves the working setup list) | `002`, `003`, `004` (apply-a-row removes it), `006` (row action) |
| US-087.AC-2 (restore brings it back) | `002`, `003`, `004`, `006` |

R2 (a setup is optional: no sentinel or default setup row is ever created; creating a
character creates no setup), R5 (owner scope at query level) and R6 (nullable
`archived_at`, no delete path, listings filter by default and take an explicit flag; the
archived row stays readable by id and through `include_archived=true`) are cited on the
DoD items that prove them. UC-068's "never destroyed" postcondition is proved under R6.

**Not delivered here:**

- **US-023.AC-2** ("the setup is available to choose when starting a session"). Sessions
  are `011`'s. 010 delivers only the listing endpoint `011`'s picker will read
  (`GET /api/characters/{character_id}/setups`). It is **not faked with a stand-in
  test**. `outcome.md` records it, and FEAT-007 is **partially delivered** until `011`.
- **UC-021, UC-022, US-024, US-025** (starting a session with a setup or none; reusing
  one across sessions) are `011`'s (brief Out).
- Setup-level notes (`015`), the setup label on a session row in the tree (`011`), and
  the setups block on the full character page (`018`) are out (brief Out).

## Build prerequisite — 009 (and 008) are planned, not built

010 binds to **009's planned files**, cited from 009's step files and not re-specified.

| 009 artifact | What 010 relies on | Needed by |
|---|---|---|
| `backend/app/db/schema.py` `characters` Table (009 `001`) | the FK target of `setups.character_id`; the parent check's scoped select | `001`, `002` |
| `backend/app/errors.py` `CharacterNotFoundError` (009 `001`) | raised by 010 for a missing or foreign **parent** character (404 `character_not_found`) | `002`, `003` |
| `backend/app/models/characters.py` (009 `001`) | the model pattern 010's models copy (stripped non-empty name, `extra="ignore"`, `SnowflakeOut`) | `001` (pattern only) |
| `backend/app/services/characters.py` (009 `002`) | the service pattern (`_now_text()`, read rollback, write `begin()`). **Not imported** (D6) | `002` (pattern only) |
| `backend/app/routers/characters.py` + its `main.py` registration (009 `003`) | 010's router is registered **after** it; router tests create characters through `POST /api/characters` | `003` |
| `frontend/src/shared/MarkdownEditor.tsx` (009 `005`) | the Description editor: props `label`, `value`, `onChange`, `readOnly` | `005` |
| `frontend/src/app/CharacterScreen.tsx` (009 `007`) | existing mode's "ready" render, into which the section is placed (D1). **Edited by `006`** | `006` |
| `frontend/src/app/characterScreenState.ts` (009 `006`) | read only: the screen's `status` / `characterId` decide whether the section renders. Not edited | `006` |
| 009's tests `tests/app/CharacterScreen.test.tsx`, `tests/app/App.test.tsx` | amended by `006` where its section changes what they observe | `006` |

- **Steps `001`–`003` (backend)** need 009's backend steps `001`–`003` delivered.
- **Step `004`** creates two new modules that import only `shared/` modules (`api.ts`,
  `apiError.ts`). It needs nothing from 009 and may be built before it.
- **Step `005`** imports 009's `shared/MarkdownEditor.tsx`, so it needs 009 `005`
  delivered.
- **Step `006`** edits 009's `CharacterScreen.tsx` and amends 009's tests, so it needs
  **009 delivered**, and therefore 008 (`App.tsx`, `WorkspaceShell.tsx`).

## Built state this feature reads (001..007 are built)

Exactly as 009's `context.md` "Built state this feature reads" lists it (`errors.py`
`DomainError`, `models/ids.py` `SnowflakeOut` / `SnowflakeIn`, `ids.py`
`SnowflakeGenerator`, `routers/bootstrap.py` `get_id_generator`, `dependencies.py`
`require_user` → `CurrentUser`, `db/engine.py` `get_connection`, `main.py`; frontend
`shared/api.ts`, `shared/apiError.ts`, `shared/IconButton.tsx`, `shared/AppProviders.tsx`,
the MobX precedents). Plus the modal precedent `src/admin/UsersPage.tsx` +
`src/admin/CreateUserModal.tsx` + `src/admin/createUserDraft.ts`.

## Wire contract — setups

`routers/setups.py`, router-level `require_user` (as 009 D6). Two path families on one
router (D5).

| Route | Body | Answers |
|---|---|---|
| `GET /api/characters/{character_id}/setups` | — | 200 `{ setups: [Setup…] }`. Working list only (`archived_at IS NULL`). `?include_archived=true` returns working **and** archived. Order: D10. The character must be the caller's (archived or not) |
| `POST /api/characters/{character_id}/setups` | `{ name, description? }` | **201** the created `Setup`. The character must be the caller's; an **archived** character is allowed (D5) |
| `GET /api/setups/{setup_id}` | — | 200 the `Setup`, **archived or not** |
| `PATCH /api/setups/{setup_id}` | `{ name?, description? }` | 200 the updated `Setup` |
| `POST /api/setups/{setup_id}/archive` | — | 200 the `Setup` (idempotent, D9) |
| `POST /api/setups/{setup_id}/restore` | — | 200 the `Setup` (idempotent, D9) |
| any `DELETE` on either family | — | **405**. No delete route exists (R6) |

`Setup` on the wire:

```
{ id: "<decimal string>", character_id: "<decimal string>", name: string,
  description: string, archived_at: string | null, created_at: string, updated_at: string }
```

Timestamps are `data-model.md`'s fixed-width form (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`).
`user_id` is **never** on the wire.

Failures:

- a `character_id` that addresses no row **or another user's character** →
  **404 `character_not_found`** (009's code), empty `detail`;
- a `setup_id` that addresses no row **or another user's setup** → **404
  `setup_not_found`** (new, D8), empty `detail`;
- a blank or whitespace-only `name` → FastAPI's native **422** (no domain code);
- a non-numeric path id → 422; no session → 401 `not_authenticated`.

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

- `docs/architecture/data-model.md`: **`setups`** (the column list; no configuration
  overrides), the **timestamp convention**, **Identifiers**, "Roleplay content" (the
  direct `user_id` column), **"`translations`, `messages`, `memos` and the archive rule"**
  (archive does not cascade), "Vector tables" (`setups.description` is a `session_vec`
  input; forward note only), "Schema drift and rebuild" (a new table reaches an existing
  DB via `Create`).
- `docs/architecture/domain-rules.md`: **R2** (a setup is optional; no sentinel/default
  setup row), **R5** (the general isolation bullet), **R6** in full.
- `docs/architecture/backend-structure.md`: "Layout" (routers group by feature),
  "Routers versus services", "Authorization as router dependencies", "The JSON id
  boundary", "The error model" and "The per-code status record", "Database access",
  "Schema evolution".
- `docs/architecture/frontend-structure.md`: "State — MobX 6", "Where a store's file
  lives", **"Routing inside the `app` entry"** ("Setups have no route"; the archive-toggle
  `_TBD:`, which **D4** settles for FEAT-007), "Ids are strings", "The API client".
- `docs/architecture/workspace-shell.md`: **"The character page"** (setups are one of its
  blocks; 010 delivers an interim section, D1).
- `docs/architecture/ui-conventions.md`: Icons (`IconButton`, the icon table: `IconPlus`,
  `IconArchive` / `IconArchiveOff`, `IconEdit`, `IconDots`), **Tables** (row actions in
  an overflow `Menu`), "Loading, errors and empty states", **"Create and edit are always
  a `Modal`"** and its open/target `useState` rule, **the MobX draft convention** and
  "Draft lifetime", "Async feedback", "Mutations are never optimistic", the confirm
  convention ("Deliberately NOT confirmed").
- `docs/architecture/search-and-retrieval.md`: the `session_vec` fan-out (a setup
  description edit will be an invalidation input; forward note only).
- `docs/product/use-cases/FEAT-007.setups.md`, `docs/product/stories/FEAT-007.setups.md`.

Cited, never copied.

## Files this feature touches

```
backend/
  app/db/schema.py                 # + setups Table literal                          (001)
  app/errors.py                    # + SetupNotFoundError                            (001)
  app/models/setups.py             # NEW — 4 pydantic models                         (001)
  app/services/setups.py           # NEW — Setup value + 6 operations                (002)
  app/routers/setups.py            # NEW — /api/characters/{id}/setups, /api/setups  (003)
  app/main.py                      # registers the setups router after characters    (003)
  tests/test_db_schema.py (010 delta), tests/test_setups_models.py,
  tests/test_admin_db_router.py (undeclared-name list: "setups" → another name)      (001)
  tests/test_setups_service.py                                                       (002)
  tests/test_setups_router.py                                                        (003)
frontend/
  src/app/setupsApi.ts             # NEW — Setup type + 5 calls                      (004)
  src/app/setupsSectionState.ts    # NEW — section data class + fns                  (004)
  src/app/setupDraft.ts            # NEW — modal draft class + fns                   (005)
  src/app/SetupModal.tsx           # NEW — create / edit modal                       (005)
  src/app/SetupsSection.tsx        # NEW — the section on the character screen       (006)
  src/app/CharacterScreen.tsx      # renders the section (existing mode, ready)      (006)
  tests/app/setupsApi.test.ts, tests/app/setupsSectionState.test.ts                  (004)
  tests/app/setupDraft.test.ts, tests/app/SetupModal.test.tsx                        (005)
  tests/app/SetupsSection.test.tsx, tests/app/CharacterScreen.test.tsx (amended),
  tests/app/App.test.tsx (amended)                                                   (006)
```

**Not touched. A step that touches one is out of scope:** every 009 backend module
(`models/characters.py`, `services/characters.py`, `routers/characters.py`),
`backend/app/dependencies.py`, `backend/app/ids.py`, `backend/app/models/ids.py`,
`backend/app/db/engine.py`, `backend/app/db/drift.py`, `backend/app/db/sync.py`, every
other router and service, `backend/tests/conftest.py` (no shared fixtures are added),
009's backend tests, `backend/tests/test_llm_registry_models.py` and
`backend/tests/test_llm_registry_servers.py` (their future-table lists do not name
`setups`; checked, no action). Frontend: `src/app/App.tsx`, `src/app/WorkspaceShell.tsx`,
`src/app/CharacterTree.tsx`, `src/app/charactersApi.ts`, `src/app/charactersState.ts`,
`src/app/characterScreenState.ts`, `src/shared/*` (including `MarkdownEditor.tsx`, used
unchanged), `src/admin/*`, `src/shell.css`, `src/global.css`, `frontend/package.json`
and the lockfile (**no new npm dependency**), `vite.config.ts`, `tests/conventions.test.ts`,
`tests/ids-are-strings.test.ts`, `tests/setup.ts`, 009's other tests.

## Cross-cutting constraints every step holds

**Owner scope lives in SQL.** Every statement that reads or writes `setups` carries
`setups.user_id = <caller's id>` in its own `WHERE` (or `VALUES` for the insert). The
parent check carries `characters.user_id = <caller's id>` in its own `WHERE`. Nothing is
fetched and filtered in Python, and nothing in the frontend filters by owner (R5). The
service takes `user_id` as a **required positional** argument.

**Routers own HTTP; services own SQL.** No SQL in `routers/setups.py`; no `fastapi` import
in `services/setups.py`; `models/setups.py` imports neither. **Services do not call each
other** (D6).

**No delete path, anywhere.** No `DELETE` route, no delete function in the service, no
`DELETE` statement against `setups`, no frontend call that deletes (R6).

**No default setup, anywhere.** Nothing creates a setup except an explicit
`POST /api/characters/{character_id}/setups`. Creating a character writes no `setups` row,
and no code path invents one (R2).

**Ids are strings in every frontend file and every JSON payload.** `Setup.id` and
`Setup.character_id` are `string`. No `parseInt`, no `id: number`, no ordering derived
from an id. The backend converts only through `SnowflakeOut` / `SnowflakeIn`.

**No context, no methods.** As 009 `context.md` states it (data classes with observable
fields only, free functions that `runInAction`, abort-aware, never reject; `useState`
instances passed as props; `observer` on every reader).

**Never optimistic.** A mutation renders only the server's returned row.

**Every icon-only control goes through `shared/IconButton`.** Tests find controls by
accessible name. The names fixed in the step files are the contract.

**TypeScript only.** No `.js` / `.jsx` / `.mjs` / `.cjs`.

## Decisions — settled, with their reasoning

Decisions cited as "009 Dn" are in `docs/plans/009.characters/context.md`.

### D1 — The setups list is a "Setups" section on 009's character screen (user decision)

`/characters/:id` in **existing mode**, once the character has loaded (`"ready"`), renders
a section headed **"Setups"** between the persona block (Name, Persona, Save,
Archive/Restore) and the empty **"Sessions"** heading. It is **absent** in new mode
(`/characters/new`: there is no character to hang a setup on) and absent in the loading,
not-found and failed states. It renders for an archived character too (D5).

There is **no setup route** (`frontend-structure.md`, "Setups have no route"): a setup
belongs to the character page (US-096). `018` later rebuilds this interim section into
the character page's setups block. Recorded in `outcome.md`.

### D2 — Create and edit happen in a Mantine `Modal` (user decision)

`ui-conventions.md`'s modal rule applies: a setup form is multi-field, and the draft-page
exception names only `/characters/new`.

- The section header carries a **labelled** button **"New setup"** (`IconPlus` as its
  left section). Labelled, not an `IconButton`, because it sits among the character
  screen's actions, which 009 renders as labelled buttons (009 `context.md`, "Every
  icon-only control…"). It opens the modal in **create** mode.
- A row's overflow menu item **"Edit"** (`IconEdit`) opens the modal in **edit** mode,
  prefilled from that row (D13).
- The modal holds a text input **"Name"** and 009's shared `MarkdownEditor` labelled
  **"Description"**. Its title is **"New setup"** / **"Edit setup"**. Its submit is
  labelled **"Create"** / **"Save"**; a **"Cancel"** button closes it.
- The modal is **conditionally mounted**, so its draft (`setupDraft.ts`) is constructed
  fresh per open (`ui-conventions.md` "Draft lifetime"). Which modal is open is
  component-local `useState` in `SetupsSection` (`createOpen` boolean, `editTarget`
  setup-or-null), never MobX (`ui-conventions.md`). Precedent: `src/admin/UsersPage.tsx`
  + `CreateUserModal.tsx` + `createUserDraft.ts`.
- A submit failure renders **inside the modal**, in an inline `Alert`, and the modal stays
  open with the typed values. On success the modal closes and the returned row is applied
  to the section state (D11).
- Edit mode sends `name` and `description` together in one `PATCH` (as 009 D2). Its
  submit is enabled only when the draft differs from the row being edited.

### D3 — Archiving a setup is always silent and always succeeds (user decision; closes the brief's open question)

No warning, no refusal, no reference count. R6: archive does not cascade
(`data-model.md`, "… and the archive rule"), so sessions that reference the setup (from
`011`) keep their `setup_id` and keep working. A refusal would make an R6 reversible
filter depend on other rows, and a warning would need a count of referencing sessions. R5
bans that query shape only for administrative surfaces, but keeping counts out of this UI
avoids putting the pattern there at all. The archive operation in `002` reads and writes
`setups` only.

Forward note for `011` (`outcome.md`): an archived setup is **not offered** when starting
a new session, but an existing session that references it **still shows its label**.

### D4 — "Show archived setups" switch in the section header, not persisted (user decision; settles `frontend-structure.md`'s archive-toggle `_TBD:` for FEAT-007)

The section header carries a Mantine `Switch` labelled **"Show archived setups"**. The
label differs from the tree's "Show archived" (009 D4) because both are on screen at once
on `/characters/:id`, and two controls with one accessible name are ambiguous. It starts
**off** and is **not persisted** (same reasoning as 009 D4). When on, the list reloads
with `include_archived=true`. Archived rows are **dimmed**, carry an **"Archived"** badge,
and their menu offers **"Restore"** (`IconArchiveOff`) in place of **"Archive"**
(`IconArchive`). No confirm on either (non-destructive; `ui-conventions.md` "Deliberately
NOT confirmed").

### D5 — The route surface (orchestrator decision)

The table in "Wire contract". `routers/setups.py` is one router (routers group by feature,
`backend-structure.md` "Layout") with router-level `require_user` and full paths for both
families. It is registered in `main.py` **after** the characters router.

- The child collection hangs off its parent (`/api/characters/{character_id}/setups`)
  because a setup is created under, and listed for, one character. The single-setup routes
  are flat (`/api/setups/{setup_id}`) because a setup id is globally unique, and a nested
  path would make the service check a parent it does not need.
- **Listing** setups of an **archived** character is allowed. **Creating** under an
  archived character is allowed too, consistent with 009 D9 (an archived character stays
  editable, and nothing forbids it).
- A setup **cannot move** to another character: `character_id` is not a field of either
  request model, so a body carrying it is ignored like any unknown key.
- Named action routes for archive/restore and `PATCH` with null ≡ absent and an empty
  PATCH as a no-op, as 009 D7.

### D6 — The setups service checks the parent with its own scoped select (orchestrator decision)

`services/setups.py` verifies the parent character with its own
`SELECT … FROM characters WHERE id = :character_id AND user_id = :user_id`, inside the
same transaction as the list read or the insert. It does **not** call
`services/characters.py`. A service operation owns its transaction (009 `002.context.md`
"Service conventions"), so calling another service's operation would either nest a
`begin()` (which raises) or split one decision across two transactions. Importing the
`characters` Table and `CharacterNotFoundError` is the only coupling.

### D7 — The `setups` table (orchestrator decision)

Eight columns, exactly `data-model.md`'s list: `id` (snowflake PK), `user_id` (FK
`users.id`, NOT NULL), `character_id` (FK `characters.id`, NOT NULL), `name` (Text NOT
NULL), `description` (Text NOT NULL, **no server default**; the service always writes it,
`""` when the request omits it), `archived_at` (Text, nullable), `created_at`,
`updated_at` (Text NOT NULL, fixed-width form). **No configuration columns** (R1;
`data-model.md` `setups`). **No `ON DELETE`** on either FK (no delete path exists, as 009
D5).

One **composite index on `(user_id, character_id)`**, non-unique. The list query filters
both columns, and the leftmost `user_id` prefix also serves every by-owner scan (the
per-user export). One index instead of two.

No DDL at startup. A fresh instance gets the table from bootstrap's `create_all`. An
existing instance reports `setups` as **missing** on the admin Database page (and
`/api/health` reports `schema: "missing"`) until an administrator presses **Create**
(FEAT-005). Recorded in `outcome.md`.

### D8 — Not-found and validation (orchestrator decision; as 009 D8)

- `setup_not_found` (404, empty `detail`) answers both "no such setup" and "another
  user's setup", indistinguishably (R5). A new `DomainError` subclass, the same shape as
  009's `CharacterNotFoundError`.
- A missing or foreign **parent** on list or create answers 009's `character_not_found`.
  It is the character the path addresses, and a second code for the same condition would
  add nothing.
- `name` is **stripped, then required non-empty** (native 422). `description` is
  markdown, **never stripped**, and may be empty. Unknown body keys are ignored
  (`user_id`, `character_id`, `archived_at` cannot be set through a body).

### D9 — Archive semantics (orchestrator decision; as 009 D9)

Archive sets `archived_at`; on an archived setup it is a **no-op keeping the original
`archived_at`**. Restore sets NULL; on a working setup it is a no-op. A state change bumps
`updated_at`; a no-op writes nothing. Editing an archived setup is allowed and leaves
`archived_at` unchanged; its row's menu keeps "Edit".

### D10 — Order: newest created first (orchestrator decision; as 009 D10)

`ORDER BY created_at DESC, id DESC`. No requirement orders setups, and this keeps the
section consistent with the tree's interim order.

### D11 — The section owns its own state (orchestrator decision)

`app/setupsSectionState.ts` holds one section's rows, load status, row-action error, the
in-flight row and the switch. `SetupsSection` creates **one** instance with
`useState(() => new SetupsSectionState(characterId))`, and `CharacterScreen` renders the
section **keyed by the character id**, so navigating between characters builds fresh
state. Setups appear nowhere else yet (the tree's setup label on a session row is
`011`'s), so no workspace-level state is needed, and `App` is not touched.

After a create, save, archive or restore, the section **applies the server's returned
row** through one pure upsert rule. It is 009 D11's rule (replace in place; remove an
archived row while the switch is off; insert an absent visible row at its `created_at`
descending position), applied to setups. No list refetch follows a mutation. This is
never-optimistic in 009 D11's narrowed form: what renders is what the server returned.

### D12 — Feedback: every 010 failure has a place of its own (as 009 D12)

The section's load failure renders inline in the section, as **"Could not load setups"**
with a **"Retry"**. A row archive/restore failure renders in an inline `Alert` in the
section (**"Could not archive the setup."** / **"Could not restore the setup."**). A modal
submit failure renders in the modal's `Alert` (**"Could not create the setup."** /
**"Could not save the setup."**). 010 adds **no `notifyFailure` call site** and no success
feedback beyond the re-rendered row. Fixed sentences per action, for 009
`006.context.md`'s reasons ("Why the error is a fixed text per action").

### D13 — The list is a table with an overflow menu per row; the empty state is one neutral line

- Rows render in a plain Mantine `Table` (`ui-conventions.md` "Tables"). Each row shows
  the setup's **name** (plus the "Archived" badge and dimming when archived) and a trailing
  overflow **`Menu`** behind one `IconDots` `IconButton` labelled **"Actions for
  <name>"**. Its items are text-labelled with their table icon as a left section:
  **"Edit"** (`IconEdit`), then **"Archive"** (`IconArchive`) or **"Restore"**
  (`IconArchiveOff`). This satisfies the user's "row actions" decision within
  `ui-conventions.md`'s rule that a table row holds exactly one icon-only control. The
  description is not shown in the row: it is markdown of any length, and the modal shows
  it.
- An empty ready list renders the line **"No setups yet."** and nothing else. It does not
  invite creating one, because a setup is optional (R2, FEAT-007). The "New setup" button
  in the header is the only affordance.

### D14 — Six steps

Backend in three (table + error + models; service; router), as 009 D14 split them, for the
same size and independent-testability reasons. Frontend in three: the API client with the
section state, the modal's draft with the modal, then the section with its hook into the
character screen. The section is last because it composes the modal and the state, and
because it is the only step that needs 009 fully delivered.

## Test landmines (harvester-confirmed)

- `backend/tests/test_admin_db_router.py`'s `UNDECLARED_NAMES` holds `"setups"` (put
  there by 009 `001` DoD-12) as an example of an unregistered table. 010 declares it, so
  `001` swaps it (its DoD-9).
- `backend/tests/test_db_schema.py` holds 006's and 009's registry-delta assertions in a
  later-table-proof form (009 `001` DoD-1 / DoD-11). 010 adds its own delta the same way,
  and keeps the earlier ones passing (`001` DoD-1, DoD-8).
- `test_llm_registry_models.py:595` and `test_llm_registry_servers.py:813` list
  `{"sessions", "characters", "memos"}` as never-touched future tables. They do not name
  `setups`, so they need no action.

## Vocabulary

| Term | Means here |
|---|---|
| **setup** | one `setups` row: a name and a markdown `description` under one character, owned by one user |
| **description** | the markdown body; the modal labels its editor "Description" |
| **parent character** | the character a setup was created under (`character_id`, fixed for life) |
| **working list** | a character's setups with `archived_at IS NULL` |
| **archived** | `archived_at` set; out of the working list, still readable by id and with `include_archived=true` |
| **the section** | the "Setups" section on the character screen (D1) |
| **the section state** | the one `SetupsSectionState` a `SetupsSection` creates (D11) |
| **the modal** | `SetupModal`, in create or edit mode (D2) |
| **Archived badge** | a Mantine `Badge` reading exactly "Archived", on an archived setup row |
| **apply a row** | upsert a server-returned `Setup` into the section state by D11's rule |

## Step map

| Step | Subject | Est. LoC | Depends on |
|------|---------|----------|------------|
| 001 | `setups` Table, `SetupNotFoundError`, `models/setups.py`, test landmines | ~85 | 009 `001` delivered |
| 002 | `services/setups.py` — value object + six operations | ~150 | 001; 009 `001` delivered |
| 003 | `routers/setups.py` + `main.py` registration | ~85 | 001, 002; 009 `001`–`003` delivered |
| 004 | `app/setupsApi.ts` + `app/setupsSectionState.ts` | ~140 | 003 (wire contract) |
| 005 | `app/setupDraft.ts` + `app/SetupModal.tsx` | ~140 | 004; 009 `005` delivered |
| 006 | `app/SetupsSection.tsx` + `CharacterScreen.tsx` hook-in | ~150 | 004, 005; 009 delivered (and so 008) |

## Test conventions

**Inherited verbatim from 009 `context.md` "Test conventions"**: the backend paragraph
(pytest from `backend/`, no shared fixtures added, schema from `create_all`, per-file
`application` / `client` fixtures with a file-local `_insert_user` and `_login`, two users
for isolation), the frontend paragraph (Vitest, `globals: false`, `tests/` mirrors `src/`,
each `it` title ends **`— DoD-N`** of its own step, `fetch` stubbed per test with
`vi.stubGlobal`, `AppProviders`, `MemoryRouter` where routed, assertions on rendered
behaviour only), and the **`vi.mock` stub of `src/shared/MarkdownEditor`** (a labelled
`<textarea>` honouring `label`, `value`, `onChange`, `readOnly`). Every 010 component test
that renders the Description editor (`005`, `006`) may use that stub.

Additions for 010:

- **FK chain.** `setups.user_id` and `setups.character_id` are real FKs with
  `foreign_keys = ON`, so every setup row needs its user row and its character row first.
  Service tests insert characters with a raw insert into the `characters` Table. Router
  tests create them through `POST /api/characters` (009's route).
- **Mantine portals.** `Modal` and `Menu` render into a portal outside the section's DOM
  subtree. Query dialogs and menu items through `screen` (`findByRole("dialog")`,
  `getByRole("menuitem", { name: … })`), not `within(section)`.
- **Scoping on the character screen.** The section is a region named **"Setups"**. The
  screen also carries the character's own "Archived" badge and the tree's "Show archived"
  switch (in `App`), so section assertions use `within(getByRole("region", { name:
  "Setups" }))`.
