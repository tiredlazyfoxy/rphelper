# Feature 009 — Characters · feature-wide context

## What this feature is

Gives the roleplayer the persona the assistant will one day compose as. A character is a
**name plus one markdown persona body** (`sheet`). It is created from an explicit form at
`/characters/new`, edited and saved on its own screen at `/characters/:id`, and listed in
the left column's tree. That list belongs to the roleplayer alone: every query is scoped
to the owner in SQL, and another user's character id answers 404. A character is archived
out of the working list and restored to it from its own screen, and nothing is ever
destroyed. No route deletes a character.

The agreed boundary is `brief.md` in this folder. Its Definition and Scope In/Out bound
every step here and are **not** widened. Its two open questions are closed by **D2** (the
persona is one markdown body) and **D4** (an archived character's page stays reachable
directly; its sessions are `011`'s, and there is a forward note in `outcome.md`).

## Product ids

`FEAT-006`, via **UC-017**, **UC-018**, **UC-019**, **UC-067**.

| Criterion | Where it lands |
|---|---|
| US-020.AC-1 (create on save) | `002` (service), `003` (route), `006` (submit), `007` (the Create form) |
| US-020.AC-2 (the new character appears in the list) | `002`, `003` (listing), `004` (upsert into the workspace list), `008` (the tree shows it) |
| US-021.AC-1 (edit + save persists) | `002`, `003`, `006`, `007`, `008` (the tree shows the new name) |
| US-022.AC-1 (the list shows only the roleplayer's own characters) | `002`, `003` (SQL scope, R5), `008` (the tree renders what the server returned) |
| US-086.AC-1 (archive leaves the working list) | `002`, `003`, `004`, `006`, `008` |
| US-086.AC-2 (restore puts it back) | `002`, `003`, `004`, `006`, `008` |
| US-086.AC-3 (never destroyed) | `002` (no delete in the service), `003` (DELETE answers 405; the archived row stays readable by id and through the include-archived listing) |

R5 (every read scoped by the owning user at query level) and R6 (archive is a nullable
`archived_at`, there is no delete path, listings filter `archived_at IS NULL` by default
and take an explicit flag) are cited on the DoD items that prove them.

**Not delivered here:**

- **US-021.AC-2** ("a later session under that character uses the updated persona").
  Sessions are `011`'s and context composition is `020`'s, so there is nothing yet that
  could read the persona. It is **not faked with a stand-in test**. `outcome.md` records
  it as a forward note.
- **UC-017 step 2/4** (a draft page that persists on first real input, UC-074, US-097)
  is `018`'s. 009 uses an explicit **Create** (D1).
- The full character page from `workspace-shell.md` ("The character page"): notes grid
  (`015`), setups (`010`), resolved configuration (`017`) and the composer that starts a
  session (`018`/`011`). 009 renders only the name, the persona editor, Save,
  Archive/Restore, the Archived badge and an empty **Sessions** heading.
- The tree's session level, its expand/collapse chevron and newest-use ordering
  (UC-069, US-088, US-089) are `011`'s.

## Build prerequisite — 008 is planned, not built

Steps **001–003 (backend)** depend only on built code (001..007) and can be built now.

Steps **004–008 (frontend)** bind to `008.app-shell-frame`. 008 is **planned but not
built**. **Steps 007 and 008 cannot be built until 008 is delivered** (they edit 008's
`App.tsx` and `WorkspaceShell.tsx` and amend 008's tests). Steps 004–006 create new modules
and touch no 008 file, but they import `shared/` modules only. They may be built before 008,
and they need nothing from it.

008's planned contract that 009 binds to (cited from 008's step files, not re-specified):

| 008 artifact | What 009 relies on |
|---|---|
| `src/app/App.tsx` (008 step `004`) | `App` takes `user` and `storage`, renders `WorkspaceShell` around flat `<Routes>` that declare `/characters/new` and `/characters/:id` with empty centres, plus a `*` "Page not found". No router of its own. **Edited by 009 `007` and `008`.** |
| `src/app/WorkspaceShell.tsx` (008 step `004`) | `observer`. Props `user`, `storage`, `children`. The nav element ("Workspace navigation") renders either the **rail** ("Search", "New character", "Expand tree", compact `UserMenu`) or the **expanded column** ("Collapse tree" on top, **an empty body**, `UserMenu` at the foot). It closes the narrow overlay on any in-entry navigation. **Edited by 009 `008`** (the empty body gets the tree). |
| `src/app/shellState.ts` (008 step `002`) | Not touched. The collapse/overlay logic is unchanged. |
| `src/shared/currentUser.ts` (008 step `001`) | `CurrentUser` (`id: string`, `username`, `role`). 009 uses it only through `App`'s existing props. |
| 008 tests `tests/app/App.test.tsx`, `tests/app/WorkspaceShell.test.tsx`, `tests/app/AppBoot.test.tsx`, `tests/entries.test.tsx` | Amended by 009 (`007`, `008`) where 009 changes what they observe. Each amendment is named in the owning step's context. |

## Built state this feature reads (001..007 are built)

Backend (harvested):

| Module | What this feature uses |
|---|---|
| `backend/app/db/schema.py` | The one `metadata`, every table a module-level `Table(...)` literal. **Extended by `001`.** |
| `backend/app/errors.py` | `DomainError` (class attrs `code`, `http_status`), its one registered handler, the precedent `UserNotFoundError`. **Extended by `001`.** |
| `backend/app/models/ids.py` | `SnowflakeOut` (response ids → decimal string), `SnowflakeIn` (request/path ids → int). |
| `backend/app/ids.py` | `SnowflakeGenerator` with `next_id()`. |
| `backend/app/routers/bootstrap.py` | `get_id_generator` — the dependency that hands a handler the process's one generator. |
| `backend/app/dependencies.py` | `require_user` → frozen dataclass `CurrentUser(id: int, username: str, role: Role)`. Answers 401 `not_authenticated`. |
| `backend/app/db/engine.py` | `get_connection` — request-scoped Core `Connection`, opens no transaction. |
| `backend/app/main.py` | App factory; registers routers. **Extended by `003`.** |

Frontend (harvested): `src/shared/api.ts` (`apiGet` / `apiPost` / `apiPatch` / `apiDelete`,
path must start `/api/`, a 401 navigates to `/login` itself then throws), `src/shared/apiError.ts`
(`ApiError` with `.code`, `isApiError`), `src/shared/notifyFailure.ts`, `src/shared/IconButton.tsx`,
`src/shared/AppProviders.tsx`, the MobX precedents `src/admin/usersPageState.ts` and
`src/admin/createUserDraft.ts`.

## Wire contract — `/api/characters`

`routers/characters.py`, prefix `/api/characters`, router-level `require_user` (D6).

| Route | Body | Answers |
|---|---|---|
| `GET /api/characters` | — | 200 `{ characters: [Character…] }`. Working list only (`archived_at IS NULL`). `?include_archived=true` returns working **and** archived. Order: D10 |
| `POST /api/characters` | `{ name, sheet? }` | **201** the created `Character` |
| `GET /api/characters/{character_id}` | — | 200 the `Character`, **archived or not** |
| `PATCH /api/characters/{character_id}` | `{ name?, sheet? }` | 200 the updated `Character` |
| `POST /api/characters/{character_id}/archive` | — | 200 the `Character` (idempotent, D9) |
| `POST /api/characters/{character_id}/restore` | — | 200 the `Character` (idempotent, D9) |
| any `DELETE` | — | **405**. No delete route exists (R6) |

`Character` on the wire:

```
{ id: "<decimal string>", name: string, sheet: string,
  archived_at: string | null, created_at: string, updated_at: string }
```

Timestamps are the fixed-width form from `data-model.md` ("Timestamps — one fixed-width
text form"): `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`. `user_id` is **never** on the wire.

Failures: an id that addresses no row **or another user's row** → **404**
`character_not_found`, empty `detail`. A blank or whitespace-only `name` → FastAPI's native
**422** (no domain code). No session → 401 `not_authenticated`.

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

- `docs/architecture/data-model.md`: **`characters`** (the column list and the
  no-language-columns rule), the **timestamp convention**, **Identifiers** (snowflakes,
  the JSON string boundary), **"`translations`, `messages`, `memos` and the archive
  rule"**, "Schema drift and rebuild" (a new table reaches an existing DB via `Create`).
- `docs/architecture/domain-rules.md`: **R5** (the general isolation bullet: scope at the
  query level, never post-filtered), **R6** in full.
- `docs/architecture/backend-structure.md`: "Layout", **"Routers versus services"**,
  "Authorization as router dependencies" (`require_user`, `user_id` a required positional
  service argument), **"The JSON id boundary"** (path ids via `SnowflakeIn`), **"The error
  model"** and "The per-code status record", "Database access" (transactional DDL, autobegun
  reads), "Schema evolution" (no DDL at startup).
- `docs/architecture/frontend-structure.md`: **"State — MobX 6, per-page stores, no
  context"**, "Where a store's file lives", **"Routing inside the `app` entry"** (and the
  archive-toggle `_TBD:` that D4 settles), **"Ids are strings"**, "The API client",
  **"Markdown"**.
- `docs/architecture/workspace-shell.md`: "The three columns" (the tree), **"The character
  page"** (only partially delivered, see above).
- `docs/architecture/ui-conventions.md`: Icons (sizing, `IconButton`, the icon table:
  `IconPlus`, `IconArchive` / `IconArchiveOff`, `IconDeviceFloppy`, `IconSearch`), "Loading,
  errors and empty states", "Create and edit are always a `Modal`" and its draft-page
  exception, **"Async feedback"**, **"Mutations are never optimistic"**, "Page state".
- `docs/product/use-cases/FEAT-006.characters.md`, `docs/product/stories/FEAT-006.characters.md`.

Cited, never copied.

## Files this feature touches

```
backend/
  app/db/schema.py                 # + characters Table literal                     (001)
  app/errors.py                    # + CharacterNotFoundError                       (001)
  app/models/characters.py         # NEW — 4 pydantic models                        (001)
  app/services/characters.py       # NEW — Character value + 6 operations           (002)
  app/routers/characters.py        # NEW — /api/characters                          (003)
  app/main.py                      # registers the characters router                (003)
  tests/test_db_schema.py (009 delta + 006 delta rescoped), tests/test_characters_models.py,
  tests/test_admin_db_router.py (undeclared-name list: "characters" → "setups")     (001)
  tests/test_characters_service.py                                                  (002)
  tests/test_characters_router.py                                                   (003)
frontend/
  src/app/charactersApi.ts         # NEW — Character type + 6 calls                 (004)
  src/app/charactersState.ts       # NEW — workspace characters data class + fns    (004)
  src/shared/MarkdownEditor.tsx    # NEW — the TipTap wrapper                       (005)
  package.json, package-lock.json  # + TipTap / @mantine/tiptap deps                (005)
  src/app/characterScreenState.ts  # NEW — screen data class + fns                  (006)
  src/app/CharacterScreen.tsx      # NEW — new / existing modes + route wrapper     (007)
  src/app/App.tsx                  # characters state + the two character routes    (007, 008)
  src/app/CharacterTree.tsx        # NEW — tree header + character level            (008)
  src/app/WorkspaceShell.tsx       # expanded body renders the tree                 (008)
  tests/app/charactersApi.test.ts, tests/app/charactersState.test.ts                (004)
  tests/shared/MarkdownEditor.test.tsx                                              (005)
  tests/app/characterScreenState.test.ts                                            (006)
  tests/app/CharacterScreen.test.tsx, tests/app/App.test.tsx (amended)              (007)
  tests/app/CharacterTree.test.tsx, tests/app/WorkspaceShell.test.tsx (amended),
  tests/app/App.test.tsx (amended), tests/app/AppBoot.test.tsx (stubs),
  tests/entries.test.tsx (stubs)                                                    (008)
```

**Not touched. A step that touches one is out of scope:** `backend/app/dependencies.py`,
`backend/app/ids.py`, `backend/app/models/ids.py`, `backend/app/db/engine.py`,
`backend/app/db/drift.py`, `backend/app/db/sync.py`, every other router and service,
`backend/tests/conftest.py` (no shared fixtures are added), `frontend/src/shell.css`,
`frontend/src/global.css`, `frontend/src/app/shellState.ts`, `frontend/src/app/UserMenu.tsx`,
`frontend/src/app/main.tsx`, `frontend/src/app/AppBoot.tsx`, every `frontend/src/shared/*`
module other than the new `MarkdownEditor.tsx`, every `frontend/src/admin/*` module,
`frontend/vite.config.ts`, `frontend/tests/conventions.test.ts`,
`frontend/tests/ids-are-strings.test.ts`, `frontend/tests/setup.ts`. The only new npm
dependencies are the six in D3. No `react-markdown` is added.

## Cross-cutting constraints every step holds

**Owner scope lives in SQL.** Every statement that reads or writes `characters` carries
`user_id = <caller's id>` in its own `WHERE` clause (or `VALUES` for the insert). Nothing
is fetched and then filtered in Python, and nothing in the frontend filters by owner
(R5, `backend-structure.md` "Routers versus services"). The service takes `user_id` as a
**required positional** argument.

**Routers own HTTP; services own SQL.** No SQL in `routers/characters.py`; no `fastapi`
import in `services/characters.py`. `models/characters.py` imports neither.

**No delete path, anywhere.** No `DELETE` route, no delete function in the service, no
`DELETE` statement against `characters`, no frontend call that deletes (R6).

**Ids are strings in every frontend file and every JSON payload.** `Character.id` is
`string`. No `parseInt`, no `id: number`, no ordering derived from an id
(`tests/ids-are-strings.test.ts` must keep passing). The backend converts only through
`SnowflakeOut` / `SnowflakeIn`.

**No context, no methods.** Every MobX class is a data class with observable fields only
(`makeAutoObservable(this, {}, { autoBind: true })`). Derivations and effects are free
functions in the same module. Each effect `runInAction`s its writes, early-returns on an
aborted signal and never rejects. Instances are created with `useState(() => …)`, never
`useMemo`, and passed as props. Every component that reads an observable is an `observer`.

**Never optimistic.** A mutation renders only the server's returned row. Nothing is written
into a store before the response arrives (`ui-conventions.md`).

**Every icon-only control goes through `shared/IconButton`.** The character screen's
actions are **labelled buttons** (with their table icon as a left section). The tree
header's Search and New character are `IconButton`s. Tests find controls by accessible
name. The names fixed in the step files are the contract.

**TypeScript only.** No `.js` / `.jsx` / `.mjs` / `.cjs`.

## Decisions — settled, with their reasoning

### D1 — Create is an explicit form at `/characters/new` (user decision)

`/characters/new` (declared by 008) renders the character screen in **new mode**: a Name
field, the persona editor and a labelled **Create** button. **Nothing is persisted until
Create.** On success the client navigates in-entry, with `replace`, to
`/characters/<returned id>`, using the id string exactly as received. With `replace`,
Back does not return to an empty form whose Create would make a duplicate.

It is **not a modal**. `ui-conventions.md`'s draft-page exception names this route, and
this interim form is its precursor. `018` later replaces Create with save-on-first-input
on the same route (UC-017 step 2/4, UC-074, US-097). Recorded in `outcome.md`.

### D2 — The persona is `name` + one markdown body `sheet`, saved explicitly (user decision; closes brief open question 1)

The persona is `characters.sheet` (markdown, per `data-model.md`), not a set of fields.
UC-017's "appearance, backstory, voice, writing style" are the roleplayer's own headings
inside that body. The screen saves **name and sheet together** in one `PATCH`, behind a
labelled **Save** button (`IconDeviceFloppy` as its left section). On success it re-renders
from the server's response.

Explicit Save rather than the workspace's blur-save. The persona is a two-field form
edited deliberately, and `ui-conventions.md`'s blur-save applies to single in-place text
fields (entries, notes). `018` may revisit this when it rebuilds the page.

### D3 — One TipTap wrapper, `src/shared/MarkdownEditor.tsx`, and the six dependencies (user decision)

The editor is `@mantine/tiptap` + `tiptap-markdown` (`frontend-structure.md` "Markdown").
Its wiring sits behind **one** small component with a plain interface: a label, a markdown
`value`, an `onChange(markdown)` and an optional `readOnly`. Screens bind to that
interface only, tests can stub it (see "Test conventions"), and `015` / `017` / `018`
reuse it unchanged.

- **Location `shared/`**: it is domain-free UI infrastructure of the same kind as
  `IconButton`. It names no route and no entity. Only entries that import it bundle it.
- **Dependencies added** (by `005`, which owns `frontend/package.json` and the lockfile):
  `@mantine/tiptap`, `@tiptap/react`, `@tiptap/pm`, `@tiptap/starter-kit`,
  `@tiptap/extension-link` (required peer of `@mantine/tiptap`), `tiptap-markdown`.
  Version constraints are in `005.context.md`.
- **No `react-markdown` in 009.** Nothing in 009 renders markdown read-only. The editor's
  `readOnly` mode covers the one non-editable moment (while a submit is in flight).

### D4 — Archive toggle in the tree header; an archived character's page still opens (user decision; settles `frontend-structure.md`'s archive-toggle `_TBD:` for FEAT-006; closes brief open question 2 for 009's part)

- The tree's header carries a **"Show archived"** switch. When on, the listing is
  requested with `include_archived=true`, and archived characters appear in the tree
  dimmed with an **"Archived"** badge.
- **Not persisted.** It lives in the workspace characters state for the page's lifetime
  (it survives collapse/expand, not a reload). It uses the same reasoning as 008's overlay
  and the wall's open state: restoring a filter on load greets the roleplayer with a
  list that is not their working list.
- `GET /api/characters/{id}` answers archived rows too, so `/characters/:id` opens an
  archived character directly. Its screen shows the **Archived** badge and **Restore**
  (`IconArchiveOff`) in place of **Archive** (`IconArchive`).
- Archive and Restore live **on the character screen**, not on tree rows. **No confirm**.
  Archiving destroys nothing (`ui-conventions.md`'s confirm convention lists only
  destructive actions).
- Brief open question 2 (an archived character's **sessions**): sessions do not exist until
  `011`. 009 establishes that the archived character's own page stays reachable.
  `outcome.md` recommends that `011` keep an archived character's sessions reachable by
  direct URL (R6: nothing destroyed). This is a recommendation, not a requirement.

### D5 — 009 declares seven of `characters`' ten columns; 017 adds the rest (user decision)

009 declares `id`, `user_id` (FK `users.id`, NOT NULL), `name` (Text NOT NULL), `sheet`
(Text NOT NULL, **no server default**; the service always writes it, `""` when the request
omits it), `archived_at` (Text, nullable), `created_at`, `updated_at` (Text NOT NULL,
fixed-width form). **`model_ref`, `system_prompt`, `tools` are deferred to `017`**. Their
encodings are 017's, and `sessions.model_ref`'s encoding is still `_TBD:` in
`data-model.md`. A column declared now would have to guess them. `rp_language` /
`preferred_language` are never declared (R1, `data-model.md`).

The FK carries **no `ON DELETE` clause**. There is no delete path for users or characters,
so a cascade would describe an event that cannot happen. One **index on `user_id`**:
every read is scoped by it. A composite with `archived_at` buys nothing at this
cardinality.

There is no DDL at startup. A **fresh** instance gets the table from bootstrap's
`create_all`. An **existing** instance reports `characters` as *missing* on the admin
Database page (and `/api/health` reports `schema: "missing"`) until an administrator
presses **Create** (FEAT-005). `017`'s three columns later reach existing databases through
**Sync**. Recorded in `outcome.md`.

### D6 — Authorization: router-level `require_user` (orchestrator decision)

`require_user` is attached **once at router level**, so a route added later cannot forget
it. Each handler also receives the `CurrentUser` to scope the service call. Any
authenticated, enabled account owns characters. An administrator is an account too, and
`backend-structure.md` lists `require_user` for "all roleplayer routers". The admin's
characters are still its own, scoped by its own id.

### D7 — The route surface is the table above (orchestrator decision)

Named action routes for archive/restore (FEAT-003's precedent: each state change hangs
off its own route and rule). `PATCH` for name/sheet (FEAT-004's precedent: one entity,
"which fields were supplied"). An explicit `null` for `name` or `sheet` in a PATCH is
treated as "not supplied". A PATCH supplying neither is a no-op answering the unchanged
character.

### D8 — Not-found is one 404, and validation is native 422 (orchestrator decision)

`character_not_found` (404, empty `detail`) answers both "no such id" and "another user's
id", and the two are indistinguishable on the wire. That is R5's no-existence-leak posture,
and it is free because the owner predicate is in the same `WHERE` as the id. It is a new
`DomainError` subclass following `UserNotFoundError`. `name` is **stripped, then required
non-empty**, so whitespace-only is rejected. The stored name is the stripped value. A
name that is only spaces is a blank name that happens to render nothing in the tree.
`sheet` is never stripped (markdown whitespace is significant) and may be empty. Unknown
body keys are ignored (`user_id`, `archived_at` cannot be set through a body).

### D9 — Archive semantics (orchestrator decision)

- **Archive** sets `archived_at` to now. On an already-archived character it is a
  **no-op that keeps the original `archived_at`**: "when was this archived" stays true.
- **Restore** sets `archived_at` to NULL. On a working character it is a no-op.
- A state-changing archive/restore bumps `updated_at`. A no-op writes nothing.
- **Editing an archived character is allowed** (no requirement forbids it). It leaves
  `archived_at` unchanged. The screen keeps the fields editable for an archived character.

### D10 — Interim list order: newest created first (orchestrator decision)

`ORDER BY created_at DESC, id DESC` (the snowflake breaks a same-microsecond tie the same
way). The tree's real order is **newest session use** (US-089, `sessions.last_used_at`),
which needs sessions. `011` replaces this. Recorded in `outcome.md`.

### D11 — One workspace characters state, created in `App`, passed as props (orchestrator decision)

`src/app/charactersState.ts` holds the workspace's character list (rows, load status,
the Show-archived flag). `App` creates **one** instance with `useState` and passes it to
the tree (through `WorkspaceShell`) and to the character screen. After a create, save,
archive or restore, the screen **applies the server's returned row** to it through one
pure upsert rule (`004`). The tree therefore updates without a list refetch and without
a refetch racing the mutation.

This is `ui-conventions.md`'s never-optimistic rule in the same narrowed form the
workspace already uses ("re-reads the edited row"). What renders is what the server
returned. Inserting a row that is not yet in the list places it at its `created_at`
position. That is the server's D10 order, and fixed-width timestamps compare correctly as
text (`data-model.md`). It is not ordering by id.

### D12 — Feedback: every 009 failure has a place of its own, so 009 adds no `notifyFailure` call site

Per `ui-conventions.md` "Async feedback": the tree's load failure renders inline in the
tree with a Retry. The screen's load failure renders in the centre with a Retry. A 404 renders
"Character not found" in the centre. Create/Save/Archive/Restore failures render in an
inline `Alert` on the screen, which stays mounted. None of them is also a notification.
There is no success feedback beyond the re-rendered row.

### D13 — The tree's header and character level

The expanded column's body (empty in 008) gets the **tree**: a header with **"Search"**
(`IconSearch`, router navigation to `/search`), **"New character"** (`IconPlus`, router
navigation to `/characters/new`) and the **"Show archived"** switch, then one row per
character. 008's D4 deferred the two actions to "the tree's contents", and
`workspace-shell.md` puts search at the top of the tree in both states. The labels match
the rail's. Each row shows the name, is a router link to `/characters/<id>`, and is marked
active (`aria-current="page"`) on its own route. **No chevron and no session rows**. Both
are `011`'s.

### D14 — Eight steps

Backend in three steps (table + error + models; service; router), because service and router
together exceed the 200-LoC ceiling and test independently (service without HTTP).
Frontend in five: API client + workspace state, the editor wrapper with its dependencies,
the screen's state module, the screen + its routes, the tree + shell. The screen's state
is split from its component for the same size reason. The tree is last because its App-level
integration DoD items need the screen.

## Vocabulary

| Term | Means here |
|---|---|
| **character** | one `characters` row: a name and a markdown persona (`sheet`) owned by one user |
| **persona** / **sheet** | the markdown body; the UI labels its editor "Persona", the column is `sheet` |
| **working list** | the owner's characters with `archived_at IS NULL` |
| **archived** | `archived_at` set; out of the working list, still readable by id and with `include_archived=true` |
| **the workspace characters state** | the one `CharactersState` instance `App` creates (D11) |
| **the tree** | the expanded column's body: header + character level (008's left column) |
| **the character screen** | the centre column at `/characters/new` (new mode) or `/characters/:id` (existing mode) |
| **Archived badge** | a Mantine `Badge` reading exactly "Archived", on an archived tree row and on an archived character's screen |
| **apply a row** | upsert a server-returned `Character` into the workspace state by D11's rule |

## Step map

| Step | Subject | Est. LoC | Depends on |
|------|---------|----------|------------|
| 001 | `characters` Table, `CharacterNotFoundError`, `models/characters.py` | ~85 | — |
| 002 | `services/characters.py` — value object + six operations | ~130 | 001 |
| 003 | `routers/characters.py` + `main.py` registration | ~80 | 001, 002 |
| 004 | `app/charactersApi.ts` + `app/charactersState.ts` | ~120 | 003 (wire contract) |
| 005 | `shared/MarkdownEditor.tsx` + the six npm dependencies | ~75 | — |
| 006 | `app/characterScreenState.ts` | ~130 | 004 |
| 007 | `app/CharacterScreen.tsx` + `App.tsx` character routes | ~150 | 004, 005, 006, 008-feature delivered |
| 008 | `app/CharacterTree.tsx` + `WorkspaceShell.tsx` + `App.tsx` | ~115 | 004, 007, 008-feature delivered |

## Test conventions

**Backend.** pytest from `backend/`. `tests/conftest.py` provides env isolation and the
`db_settings` / `db_engine` fixtures only, and **no shared fixtures are added**. Schema
in tests comes from `schema.metadata.create_all` against the test engine, as existing tests
do. Each router test file builds its own `application` / `client` fixtures, seeds users
with a file-local raw `_insert_user`, and logs in through `POST /api/auth/login` with a
file-local `_login`. `backend/tests/test_admin_users_router.py` is the pattern. Isolation
tests need **two** users. `characters.user_id` is a real FK with `foreign_keys = ON`, so
every character row needs its user row first.

**Frontend.** Vitest inside `frontend/vite.config.ts` (`environment: "jsdom"`,
**`globals: false`**: `describe` / `it` / `expect` / `vi` imported from `"vitest"`). Tests
under `frontend/tests/` mirror `src/`. Each `it` title ends **`— DoD-N`** of its own step.
`fetch` is stubbed per test with `vi.stubGlobal`. No network-mocking library. Components
render inside `shared/AppProviders`, and routed ones inside a `MemoryRouter`.
`tests/setup.ts` polyfills `matchMedia`, `ResizeObserver`, `scrollIntoView`. Tests assert
rendered behaviour (roles, accessible names, text, router location), never internal
structure.

**TipTap in jsdom.** jsdom has no layout and only partial `contenteditable` / selection
support, so typing into ProseMirror through `user-event` is unreliable. The approach is:

- `005`'s own tests exercise `MarkdownEditor` for what jsdom does reliably: markdown in →
  rendered structure, read-only mode, and no `onChange` echo on mount or external value
  change. Real typing and toolbar use are `[manual/live]`.
- Every **other** component test that renders the persona editor (`007`, `008`) **may
  replace `src/shared/MarkdownEditor` with a stub through `vi.mock`**: a labelled
  `<textarea>` honouring `label`, `value`, `onChange` and `readOnly`. That binds to the
  component's interface only. This is the sanctioned way to drive persona edits in screen
  and App tests.
