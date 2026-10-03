# Feature 015 — Memos · feature-wide context

## What this feature is

Gives the roleplayer standing context that never has to be re-explained. A **note** (a
`memos` row) is one body of markdown with no title, created at one of four **levels**:
user, character, setup or session. It is edited in the shared TipTap editor, whose
WYSIWYG rendering is the project's live preview. Two independent flags govern it,
`is_enabled` and `is_forced`. Disabling never touches `is_forced`, so re-enabling
restores the mode the note had. A new note is enabled and not forced. A session's
**chain** resolves across all four levels with one owner-scoped query, and degrades to
three levels with no gap when the session has no setup (R2). Each note states its
**reach** (forced, searchable or disabled) with `is_enabled` checked first (R3).

"Note" and "memo" mean the same row: the product says note, the schema says `memos`.

The agreed boundary is `brief.md` in this folder. Its Definition and Scope In/Out bound
every step and are **not** widened. Its two open questions are closed by **D4** (how the
sort key is allocated, and how `016` re-allocates it) and **D1** (where user-level notes
are edited before `017`: on the session screen's chain).

## Product ids

`FEAT-012` via **UC-042**, **UC-043**, **UC-044**, **UC-046**.

| Criterion | Where it lands |
|---|---|
| US-049.AC-1 (save a note at the user level) | `002` (create, `scope_id` = caller), `004` (route), `006` (create effect), `008` ("Your notes" group on the session screen) |
| US-050.AC-1 (save a note on a character) | `002`, `004`, `006`, `008` ("Character notes"), `009` (character page) |
| US-051.AC-1 (save a note on a setup) | `002`, `004`, `006`, `008` ("Setup notes") |
| US-052.AC-1 (save a note on a session) | `002`, `004`, `006`, `008` ("Session notes") |
| US-053.AC-1 (a new note is enabled and not forced) | `001` (column defaults), `002`, `004` (flags sent on create are ignored), `006` (create sends no flags), `007` (a saved new note shows the searchable reach) |
| US-056.AC-1 (markdown with a live preview) | `007` (each note is edited in `shared/MarkdownEditor`, TipTap WYSIWYG; `frontend-structure.md` "Markdown") — structural `[test]` plus a `[manual/live]` render check |
| US-057.AC-1 (no setup → user + character + session, no gap) | `003` (one query, setup term absent), `004` (three levels on the wire), `008` (no "Setup notes" group) |
| US-101.AC-1 / AC-2 (re-enable restores forced / not forced) | `002` (an `is_enabled` update never writes `is_forced`), `004`, `006` (the enable toggle sends `is_enabled` alone), `007` (the forced control of a disabled note stays visible and reflects its flag) |
| US-119.AC-1 (one body, no title, name or header field) | `001` (no `title` column; no title field in any model), `007` (a note renders exactly one text field) |

UC-042 is realised by `002`/`004` (create) and `006`/`007` ("New note", then the body
saves on blur). UC-043 by `007` (in-place edit) and D5 (save on blur). UC-044 by `002`
(PATCH a subset of flags) and `006`/`007` (two independent toggles). UC-046 by `003`
(resolution) and `008` (the chain shown on the session screen). R2, R3 and R5 are cited on
the DoD items that prove them.

**Not delivered here. Recorded as forward notes, never faked with stand-in tests:**

- **UC-045, US-054, US-055, US-098** (a forced note reaches the system prompt; a disabled
  one does not): `020.context-assembly`. 020 selects `is_enabled AND is_forced`, gating on
  `is_enabled` first (`llm-and-streaming.md` "Forced-memo selection: is_enabled gates
  first"). It may call `services/memo_chain.py`'s `resolve_chain` and `memo_reach` (`003`)
  rather than re-deriving them.
- **US-099, US-100** (searchable notes reach `memo_search`; disabled ones never do):
  `026.memo-search-tool`.
- **UC-075, UC-076, US-102, US-103, US-104** (the note wall, its cards, reordering, in-place
  edit on the wall): `016.note-wall`. 016 moves the session screen's Notes section (`008`)
  into the wall and adds the reorder route (D4).
- **UC-046 step 3** (the chain feeds context and `memo_search`): `020` / `026`.
- **Embedding a note** (memo + embedding in one transaction, `backend-structure.md` "The
  two transaction rules"): `024`. Two consequences for 024, recorded in `outcome.md`: the
  create and body-edit routes gain a `no_embedding_model` failure, and **deleting a memo
  (D2) must also delete its `memo_vec` and `memo_fts` rows** in the same transaction.
- **The settings-screen mount for user-level notes**: `017`. **The character page's card
  grid**: `018`. Both reuse `007`'s `MemoLevelGroup` and `006`'s state, so nothing forks.
- **The orphan-scope check** (`data-model.md` "### `memos`"): deferred, unowned (D3).

## Build prerequisites

Built and committed: 001..010. **011 is mid-build**: the `sessions` Table is committed in
`app/db/schema.py`; `services/sessions.py` and `routers/sessions.py` exist as uncommitted
stubs; `SessionScreen.tsx` / `sessionScreenState.ts` do **not** exist yet (011 step `009`
plans them). 012..014 are planned, not built. 015 binds to 011's **planned** contracts,
cited from its step files and not re-specified. The roadmap's build order puts 015 after
014, so 013 `007` (which mounts `SessionStream` in the session screen) may or may not have
landed when `008` is built. `008` is written to work either way.

| Upstream artifact | What 015 relies on | Needed by |
|---|---|---|
| `backend/app/db/schema.py`: `users`, `characters`, `setups`, `sessions` Tables (committed) | parent-level checks (`002`), the session lookup (`003`), the `memos.user_id` FK | `001`, `002`, `003` |
| `backend/app/errors.py`: `CharacterNotFoundError`, `SetupNotFoundError`, `SessionNotFoundError` (committed or in 011's working tree) | raised for a missing or foreign target level | `002`, `003`, `004` |
| 009 / 010 / 011 routers (`POST /api/characters`, `POST /api/characters/{id}/setups`, `POST /api/characters/{id}/sessions`) + their `main.py` registration | router tests build the parent chain through real routes | `004` |
| 011 `009`: `frontend/src/app/SessionScreen.tsx` (`SessionScreen`, `SessionRoute` keyed by id, the ready render) | the Notes section mounts in the ready render | `008` |
| 011 `009` / 013 `007` tests: `tests/app/SessionScreen.test.tsx`, `tests/app/App.test.tsx`, `tests/entries.test.tsx` | amended where the Notes section changes what they observe (`008.context.md`) | `008` |
| 009 `007` / 010 `006` / 011 `008`: `frontend/src/app/CharacterScreen.tsx` (ready render: persona, `SetupsSection`, then `SessionsSection` keyed by `characterId`) | the Notes section mounts after `SessionsSection` | `009` |
| 009 / 010 / 011 tests `tests/app/CharacterScreen.test.tsx`, `tests/app/App.test.tsx` | amended for the extra notes request (`009.context.md`) | `009` |

- **Steps `001`–`003`** need only the committed schema Tables and the three existing
  not-found errors.
- **Step `004`** needs 009, 010 and 011 steps `001`–`003` delivered (its tests create
  characters, setups and sessions through their routes).
- **Steps `005`–`007`** import only `shared/` modules and 015's own modules. They can be
  built before 011's frontend (tests stub `fetch`).
- **Step `008`** edits `SessionScreen.tsx`: needs **011 `009` delivered**.
- **Step `009`** edits `CharacterScreen.tsx`: needs **009, 010 and 011 `008` delivered**.

## Built state this feature reads

- Backend: `app/errors.py` `DomainError` (class-level `code` / `http_status`, a fixed
  default message set in `__init__`); `app/models/ids.py` `SnowflakeOut` / `SnowflakeIn`;
  `app/ids.py` `SnowflakeGenerator`; `app/routers/bootstrap.py` `get_id_generator`;
  `app/dependencies.py` `require_user` → `CurrentUser`; `app/db/engine.py`
  `get_connection`; `app/main.py` (router registration list); `app/db/schema.py`'s one
  `metadata` and its id / FK / boolean / timestamp column forms.
- Backend references, read for pattern only and **not imported**: `app/models/setups.py`,
  `app/services/setups.py`, `app/routers/setups.py`, `tests/test_setups_service.py`,
  `tests/test_setups_router.py`. Their conventions are the harvest's and are summarised in
  each backend step's context.
- Frontend: `src/shared/api.ts` (`apiGet` / `apiPost` / `apiPatch` / `apiDelete`, path,
  optional body, optional signal; non-2xx → `ApiError`; 204 → `undefined`);
  `src/shared/apiError.ts` (`ApiError`, `isApiError`); `src/shared/IconButton.tsx`
  (`icon`, `label`, `onClick`, `disabled?`, `color?`, `sizeVariant?`);
  `src/shared/MarkdownEditor.tsx` (`label`, `value`, `onChange(markdown)`, `readOnly?`;
  `onChange` fires on user edits only; no blur handling of its own);
  `src/shared/AppProviders.tsx`.
- Frontend references, pattern only: `src/app/setupsApi.ts`,
  `src/app/setupsSectionState.ts`, `src/app/SetupsSection.tsx`,
  `tests/app/SetupsSection.test.tsx` (the `MarkdownEditor` `vi.mock`).

## Wire contract — memos

`routers/memos.py`, router-level `require_user`, full literal paths (D9).

| Route | Body / query | Answers |
|---|---|---|
| `GET /api/memos?scope=<scope>&scope_id=<id>` | `scope_id` omitted for `user`, required otherwise | 200 `{ memos: [Memo…] }`: one level's notes, ordered `sort_key, id`, disabled ones included |
| `POST /api/memos` | `{ scope, scope_id?, body }` | **201** the created `Memo`, `is_enabled` true and `is_forced` false whatever else was sent (US-053) |
| `PATCH /api/memos/{memo_id}` | any subset of `{ body, is_enabled, is_forced }` | 200 the `Memo` |
| `DELETE /api/memos/{memo_id}` | — | **204**, no body (D2) |
| `GET /api/sessions/{session_id}/memo-chain` | — | 200 `{ levels: [ { scope, scope_id, memos: [Memo…] } … ] }`, in the fixed order user, character, setup, session; **three** levels when the session has no setup, four otherwise; every note included, disabled ones too (R3 constrains the assistant, not the owner) |

`scope` is exactly one of `"user"`, `"character"`, `"setup"`, `"session"`.

`Memo` on the wire, exactly nine keys:

```
{ id: "<decimal string>", scope: "user" | "character" | "setup" | "session",
  scope_id: "<decimal string>" | null,      // null exactly when scope is "user"
  body: string, is_enabled: boolean, is_forced: boolean,
  sort_key: number, created_at: string, updated_at: string }
```

A chain level's `scope_id` follows the same rule (null for the user level; the character,
setup or session id otherwise). `user_id` is **never** on the wire, and so the stored
`scope_id` of a user-level note (which equals the caller's id) is never sent either.
`sort_key` is a small non-negative integer, not an id, and crosses as a JSON number.
Timestamps are the fixed-width form (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`).

Request rules (D15): unknown body keys are ignored; `body` is required on POST and must be
non-blank (empty or whitespace only → 422), and is stored **verbatim**; on PATCH a supplied
`body` must be non-blank too, and a key sent as `null` counts as not supplied. A non-user
`scope` with no `scope_id` → 422; for `scope="user"` a supplied `scope_id` is ignored (the
target is the caller). An unknown `scope` → 422.

Failures (`{ error: { code, message, detail } }`, `detail` always `{}`):

| Code | Status | When |
|---|---|---|
| `character_not_found` | 404 | a `character` target (list or create) that is missing **or another user's** (009's code) |
| `setup_not_found` | 404 | a `setup` target that is missing or another user's (010's code) |
| `session_not_found` | 404 | a `session` target, or the chain's session, missing or another user's (011's code) |
| `memo_not_found` | 404 | PATCH / DELETE on a memo id that is missing or another user's (**new**, D12) |
| — | 422 | blank body, non-user scope without `scope_id`, unknown scope, non-numeric id |
| `not_authenticated` | 401 | no login cookie |

An **archived** character, setup or session is a valid target for list, create and chain
(D8).

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

- `docs/architecture/domain-rules.md`: **R2** (the chain is a union over the levels that
  exist; the no-setup case is the same query with one term fewer; no sentinel setup),
  **R3** (two booleans; `is_enabled` gates first; disabling keeps `is_forced`; defaults
  enabled / not forced; the owner's own UI sees disabled notes), **R5** (owner scope in
  SQL), **R6** (memos do not archive; the contrast paragraph).
- `docs/architecture/data-model.md`: **"### `memos`"** (columns, no `title`, `sort_key`
  scoped within `(scope, scope_id)`, the polymorphic scope pair and its referential-
  integrity trade, the orphan-check paragraph, no `archived_at`), **"`translations`,
  `messages`, `memos` and the archive rule"** (no cascade), **Identifiers**, the
  **timestamp convention**, "FTS5 tables" / "Vector tables" (`memo_fts`, `memo_vec`: 024's).
- `docs/architecture/backend-structure.md`: "Layout" (`routers/memos.py`,
  `services/memo_chain.py`), "Routers versus services", "Authorization as router
  dependencies", "The JSON id boundary", "The error model" with its three `detail` rules
  (no disabled memo body in `detail`) and "The per-code status record", "The two
  transaction rules" (memo + embedding is 024's), "The logging call site" (ids, codes and
  counts, never text).
- `docs/architecture/frontend-structure.md`: "Routing inside the `app` entry", "State —
  MobX 6" (four rules), "Where a store's file lives", "Ids are strings", "The API client",
  **"Markdown"** (TipTap via `@mantine/tiptap` + `tiptap-markdown` is UC-043's editor with
  live preview).
- `docs/architecture/workspace-shell.md`: **"The wall's contents"** (two icons per note,
  the reach line, level order, edited in place and saved on focus loss, created enabled
  and not forced, nothing persisted for an empty note), "The character page" ("the same
  components in a different arrangement").
- `docs/architecture/ui-conventions.md`: `IconButton`, the icon table ("Note forced / not
  forced" `IconPin`; "Note enabled / disabled" `_TBD:`, closed provisionally by D14),
  "Loading, errors and empty states", "Async feedback" (no success toasts; a failure with a
  place of its own is not a notification), "Mutations are never optimistic".
- `docs/architecture/llm-and-streaming.md`: "Forced-memo selection: is_enabled gates
  first" (cited only; assembly is 020's).
- `docs/architecture/deployment.md`: the logging redaction rule.
- Product: `use-cases/FEAT-012.memos.md`, `stories/FEAT-012.memos.md`.

Cited, never copied.

## Files this feature touches

```
backend/
  app/db/schema.py               # + memos Table literal                              (001)
  app/errors.py                  # + MemoNotFoundError                                (001)
  app/models/memos.py            # NEW — scope literal + request / response models    (001)
  app/services/memos.py          # NEW — Memo value; create / list / update / delete  (002)
  app/services/memo_chain.py     # NEW — resolve_chain (R2) + memo_reach (R3)         (003)
  app/routers/memos.py           # NEW — the five routes                              (004)
  app/main.py                    # registers the memos router last                    (004)
  tests/test_db_schema.py (015 delta), tests/test_memos_models.py,
  tests/test_admin_db_router.py (checked; conditional)                                (001)
  tests/test_memos_service.py                                                         (002)
  tests/test_memo_chain_service.py                                                    (003)
  tests/test_memos_router.py                                                          (004)
frontend/
  src/app/memosApi.ts            # NEW — Memo types + five calls                      (005)
  src/app/memoReach.ts           # NEW — pure reach + its statement                   (005)
  src/app/memoLevelState.ts      # NEW — one level's data class + effects             (006)
  src/app/MemoLevelGroup.tsx     # NEW — the shared level group component             (007)
  src/app/memoChainState.ts      # NEW — the chain's data class + load                (008)
  src/app/MemoChainSection.tsx   # NEW — the Notes section on the session screen      (008)
  src/app/SessionScreen.tsx      # mounts MemoChainSection in the ready render        (008)
  src/app/CharacterNotesSection.tsx  # NEW — character-level Notes on the character page (009)
  src/app/CharacterScreen.tsx    # mounts it after SessionsSection                    (009)
  tests/app/memosApi.test.ts, tests/app/memoReach.test.ts                             (005)
  tests/app/memoLevelState.test.ts                                                    (006)
  tests/app/MemoLevelGroup.test.tsx                                                   (007)
  tests/app/memoChainState.test.ts, tests/app/MemoChainSection.test.tsx,
  tests/app/SessionScreen.test.tsx, tests/app/App.test.tsx,
  tests/entries.test.tsx (checked; conditional)                                       (008)
  tests/app/CharacterNotesSection.test.tsx, tests/app/CharacterScreen.test.tsx,
  tests/app/App.test.tsx                                                              (009)
```

**Not touched. A step that touches one is out of scope:**

- Backend: every 009 / 010 / 011 / 012 module (`models/`, `services/`, `routers/` for
  characters, setups, sessions, stream / messages / settle / parens), `services/auth.py`,
  `dependencies.py`, `ids.py`, `models/ids.py`, `db/engine.py`, `db/drift.py`,
  `db/sync.py`, every other router and service, **`backend/tests/conftest.py`** (no shared
  fixtures), 009 / 010 / 011 / 012 tests, `tests/test_llm_registry_models.py` and
  `tests/test_llm_registry_servers.py` (their `{"sessions", "characters", "memos"}` string
  set is a plain literal; registering `memos` is expected not to affect it, as 011 found
  for `sessions`). No new Python dependency.
- Frontend: `src/app/App.tsx` (the session route wrapper lives in `SessionScreen.tsx`),
  `WorkspaceShell.tsx`, `CharacterTree.tsx`, `UserMenu.tsx`, `AppBoot.tsx`, `main.tsx`,
  `sessionsApi.ts`, `sessionsState.ts`, `sessionScreenState.ts`, `SessionsSection.tsx`,
  `sessionsSectionState.ts`, `charactersApi.ts`, `charactersState.ts`,
  `characterScreenState.ts`, `setupsApi.ts`, `setupsSectionState.ts`, `SetupsSection.tsx`,
  `SetupModal.tsx`, every 013 / 014 module (`streamApi.ts`, `streamState.ts`,
  `SessionStream.tsx`, …), **`src/shared/*`** (including `MarkdownEditor.tsx`,
  `IconButton.tsx`, `api.ts`, `notifyFailure.ts`), `src/admin/*`, `src/shell.css`,
  `src/global.css` (no stylesheet, no selector, no `.css` file), `vite.config.ts`,
  **`frontend/package.json` and the lockfile** (no new npm dependency: no
  `react-markdown` use, no `@dnd-kit` — 016's), `tests/setup.ts`,
  `tests/conventions.test.ts`, `tests/ids-are-strings.test.ts`, every other test file not
  listed above.
- The `/settings` route and the user menu (017's). Nothing in 015 renders at `/settings`.

## Cross-cutting constraints every step holds

**Owner scope lives in SQL (R5).** Every statement that reads, writes or deletes `memos`
carries `memos.user_id = <caller>` in its own `WHERE` (or `VALUES` for the insert),
including the `MAX(sort_key)` read. Each target-level check carries that parent table's
own `user_id` predicate: `characters.user_id`, `setups.user_id` (a setup id identifies its
character, so no character predicate is needed), `sessions.user_id`. Nothing is fetched
and then filtered in Python; nothing in the frontend filters by owner. Services take
`user_id` as a **required positional** argument. A missing row and another user's row take
the same path and raise the same error.

**Routers own HTTP; services own SQL.** No SQL in `routers/memos.py`; no `fastapi` import
in either service; `models/memos.py` imports neither routers nor services, and
`db/schema.py` imports nothing from `models/`. Service isolation is D11.

**No archive on memos (R6).** No `archived_at`, no `state`, no `title` column; no archive
route. Removal is the explicit delete of D2 and nothing else. Archiving a parent changes
nothing on its notes, and an archived parent is a valid target (D8).

**`is_enabled` gates first (R3).** No code path writes `is_forced` as a consequence of
writing `is_enabled`. Every reach derivation (`memo_reach`, `memoReach`) checks
`is_enabled` before consulting `is_forced`.

**No memo body in a log line or an error `detail`.** Logging passes ids, codes and counts
only (`deployment.md`); every 015 error carries an empty `detail`
(`backend-structure.md`'s third `detail` rule).

**Ids are strings in every frontend file and every JSON payload.** `Memo.id`,
`scope_id`, every chain level's `scope_id` and every argument naming an id are `string`
(or `null`). No `parseInt`, no `id: number`, no client-side ordering: the client renders
the server's order and appends a created note at the end (D4 guarantees that is its
place).

**Pure data contracts.** Data classes with observable fields only (`makeAutoObservable`),
every derivation and effect a free function taking the state first; effects `runInAction`
their writes, check `signal?.aborted` before writing, swallow aborts and **never reject**.
One instance per mount via `useState(() => new …)`, passed as a prop, no React context,
`observer` on every reader.

**Never optimistic (D5).** What renders is what the server returned. A mutation writes the
returned row (or removes the deleted one); nothing is written in anticipation and nothing
is refetched after a mutation.

**Every icon-only control goes through `shared/IconButton`.** Tests find controls by
accessible name; the names in the UI strings table are the contract.

**No notification anywhere in 015.** Every failure has a place of its own (D5, the strings
table). `notifyFailure` is not imported.

**TypeScript only.** No `.js` / `.jsx` / `.mjs` / `.cjs`.

## UI strings — the contract tests bind to

Exact text. Components render these and nothing else for these purposes.

| Where | String | Role / element |
|---|---|---|
| Session screen | region **"Notes"** with heading **"Notes"** | `008` |
| Session screen level groups | regions **"Your notes"**, **"Character notes"**, **"Setup notes"**, **"Session notes"**, in that order; "Setup notes" **absent** when the session has no setup | each a `MemoLevelGroup` region named by its heading (`007`, `008`) |
| Character page | region **"Notes"** with heading **"Notes"** | one `MemoLevelGroup` (`009`) |
| A group's notes | a `list`; each note one `listitem` (the unsaved new note too) | `007` |
| Note editor | the `MarkdownEditor` labelled **"Note"** (saved notes and the new note alike) | `007` |
| Create | labelled button **"New note"** (`IconPlus` left section) | `007` |
| Enabled toggle | `IconButton` **"Disable note"** (`IconCircleCheck`) while enabled; **"Enable note"** (`IconCircleOff`) while disabled | `007`, D14 |
| Forced toggle | `IconButton` **"Force note"** (`IconPin`) while not forced; **"Stop forcing note"** (`IconPin`, coloured) while forced | `007`, D14 |
| Reach line | **"Forced: always given to the assistant."** / **"Searchable: found only when the assistant searches."** / **"Disabled: never reaches the assistant."** | text under the note (`005` produces it, `007` renders it) |
| Empty level | **"No notes yet."** | dimmed text in the group (`007`) |
| Load failure | **"Could not load notes"** + button **"Retry"** | in the section (`008`) or the group (`009`) |
| Save failure (create or body edit) | **"Could not save the note."** | inline under that note (`007`) |
| Delete failure | **"Could not delete the note."** | inline under that note (`007`) |
| Flag failure | **"Could not change the note."** | inline under that note (`007`) |

## Decisions — settled, with their reasoning

"011 Dn" are in `docs/plans/011.rp-sessions/context.md`; "012 Dn" in
`docs/plans/012.messages-and-settle/context.md`; "010 Dn" in
`docs/plans/010.setups/context.md`.

### D1 — Where notes are edited in 015: the session screen's chain, and the character page (user decision; closes brief open question 2)

- **Session screen.** 011's `SessionScreen` ready render gains a **Notes** section that
  shows the session's resolved chain as level groups in the fixed order user → character
  → setup → session. With no setup, the setup group is **absent**, not an empty
  placeholder (R2, US-057). Every group can create notes, edit them and toggle both
  flags. This is where **user-level notes** are edited until `017`'s settings screen
  exists.
- **Character page.** `CharacterScreen` gets a character-level **Notes** section (one
  level only), placed after the Sessions section and keyed by the character id.
- **One shared level-group component and one shared level state** serve both mounts
  (`MemoLevelGroup`, `MemoLevelState`), so there is no fork (`workspace-shell.md` "the
  same components in a different arrangement").
- Forward: `016` moves the session screen's section into the wall's cards; `017` adds the
  settings mount for the user level; `018` the character page's card grid. Each reuses
  the shared component and state.

### D2 — Nothing is persisted for an empty note; clearing a saved note deletes it (user decision)

- A new note sends **no request** until its body is non-blank: a blank new note that loses
  focus is simply dropped (`workspace-shell.md` "Nothing is persisted for an empty note").
- **Clearing all text of a saved note deletes it** (user's choice). At save time, a saved
  note whose editor text is blank is removed with `DELETE /api/memos/{memo_id}` (204). The
  server refuses a blank body on POST and PATCH (422), so blank is **never a stored
  state** and the delete is always explicit.
- **Contrast with R6, deliberate:** characters, setups and sessions never delete because
  they archive. Memos have **no archive state at all** (R6's own contrast paragraph), so
  delete is their only removal. No confirm dialog: the gesture is "erase every character
  of the text", which is its own confirmation, and `ui-conventions.md`'s confirm list
  covers administrative actions.
- The product layer has no delete-a-note story. `outcome.md` flags it for `/product-spec`
  as a plan-time user decision.
- Forward (`024`): deleting a memo must also delete its `memo_vec` / `memo_fts` rows in
  the same transaction.

### D3 — The orphan-scope check is deferred and remains unowned (user decision)

Not in 015. `data-model.md` names "the feature that creates `memos`" as the check's owner.
015 does not build it, so the ownership is open again. `outcome.md` records it for
`/roadmap` / `/architect` to place. Orphans cannot arise yet: no character, setup or
session is ever deleted (R6), and create validates the target level (`002`).

### D4 — `sort_key` allocation (user decision; closes brief open question 1)

`sort_key` is INTEGER NOT NULL. A new note gets `COALESCE(MAX(sort_key), -1) + 1` over the
caller's notes at the same `(scope, scope_id)`, computed **inside the create transaction**.
So a level's first note is 0. Lists and the chain order by `sort_key, id`. Deleting leaves
gaps, which is harmless. The column has **no unique constraint**: `016`'s reorder will
rewrite a level's whole order as 0..n-1 in one transaction, and a unique index would
collide mid-rewrite. No reorder route in 015.

### D5 — Saving: on focus loss, never optimistic, failures inline, nothing typed is lost (orchestrator decision; details refined here)

- A saved note's body **saves when focus leaves its editor, if the text changed**
  (`workspace-shell.md` "edited in place, saved on focus loss"; UC-043 step 4). Unchanged
  text sends nothing; blank text deletes (D2).
- A new note POSTs when focus leaves it with non-blank text (D13).
- **Never optimistic.** The returned row replaces the held one. A returned row is applied
  **only if its `updated_at` is not older than the held row's** (fixed-width text compare):
  a body save and a flag toggle on the same note can be in flight together, and a late
  response from the earlier write must not overwrite the later one.
- **A failure shows inline under that note and keeps the typed text** in the editor;
  focusing out again retries.
- **Mutations are never aborted.** Loads take an `AbortController` aborted on unmount;
  saves, deletes and toggles take no signal, because a save that has started must reach
  the server even if the screen is left.
- **Leaving keeps the edit.** When a level group unmounts (navigation, or the session
  route re-keying), any note whose text differs from its body, and a non-blank new note,
  are saved by the same rules (a flush). Blur is not reliably fired when an element is
  removed from the DOM, so the flush is what makes "nothing typed is lost" true.

### D6 — Flags: two independent controls; PATCH takes any subset (orchestrator decision)

`PATCH /api/memos/{id}` takes any subset of `{ body, is_enabled, is_forced }` and writes
only what was supplied. **Disabling never touches `is_forced`** (US-101): the enable
toggle sends `{ is_enabled }` alone, the forced toggle `{ is_forced }` alone. Two
controls, never a tri-state (R3, `workspace-shell.md` "Two independent icons per note").
Both are always shown, including the forced control of a disabled note, whose label still
says whether it is forced (the state that re-enabling restores). The forced toggle stays
usable while a note is disabled: the axes are independent.

### D7 — The reach line: a pure frontend helper plus a backend twin (orchestrator decision; statements fixed here)

`app/memoReach.ts` derives `"forced"` / `"searchable"` / `"disabled"` from the two flags,
checking `is_enabled` first, and maps each to its one-line statement (the strings table).
`services/memo_chain.py` carries the same three-way derivation as `memo_reach`, for 020 and
026 to reuse. It costs a few lines, and a second hand-written copy of R3's ordering in
those features would be the place the disabled-plus-forced bug comes back. Both are
tested over all four combinations; disabled-plus-forced is disabled.

The statements describe what each reach **does** in the product. Until 020 and 026 land,
the forced and searchable statements describe behaviour that does not happen yet. That is
accepted: the line states the contract the note is set to, and changing the wording
later would be churn. `outcome.md` notes it.

### D8 — Creating on an archived parent is allowed (orchestrator decision)

Archive does not cascade, and restore must return the object fully usable
(`data-model.md` "… and the archive rule", R6). So list, create and chain work on an
archived character, setup or session. No new conflict error. The same reasoning as
010 D5 / 011 D2 for creating under an archived character.

### D9 — The route surface (orchestrator decision)

The Wire contract table. One router, `routers/memos.py`, registered in `main.py` **after
every router already in the list** (it shares no path shape with any of them; see
`004.context.md`). Memo routes are flat because a memo id is globally unique, and the
level is a body or query field rather than a path segment because the scope is
polymorphic: one path family serves four levels. **The chain route lives in
`routers/memos.py`** although its path starts `/api/sessions/`: routers group by feature,
not by path prefix (`backend-structure.md`, the same reason `routers/sessions.py` owns
`POST /api/characters/{id}/sessions`), and 011's router stays untouched.

### D10 — The `memos` table (orchestrator decision; scope constraint chosen here)

Ten columns: `id` (snowflake PK, the registry id form), `user_id` (FK `users.id`, NOT
NULL, no `ON DELETE`), `scope` (NOT NULL), `scope_id` (NOT NULL, the registry's id column
type, **no FK**: polymorphic, `data-model.md`), `body` (Text, NOT NULL), `is_enabled`
(Boolean, NOT NULL, default true, server default true), `is_forced` (Boolean, NOT NULL,
default false, server default false), `sort_key` (Integer, NOT NULL, no default: the
service always allocates it, D4), `created_at`, `updated_at` (Text, NOT NULL). **No
`title`, no `archived_at`, no `state` column** (`data-model.md` forbids each).

**`scope` carries a database CHECK** through a non-native SQLAlchemy `Enum` of the four
values with the constraint created (the `users.role` precedent), not the plain-Text
`llm_servers.kind` form. Reasoning: `kind` is a provider label where a third value is a
foreseeable non-architectural change, so its CHECK would have been friction. The four
scopes are **R2's chain itself**: a fifth level is an architecture change, and a row with
any other scope would be a note that no chain query ever finds, silently. The constraint
makes that row unwritable. The drift report does not compare CHECK text, so the constraint
costs nothing there. The four values are written twice, in `db/schema.py` and in
`models/memos.py`'s literal (`db/` must not import `models/`); `001` pins their equality
with a test.

**One composite non-unique index on `(user_id, scope, scope_id, sort_key)`**: the level
list filters the first three and orders by the fourth; each chain OR-term is the same
three-column prefix; and the `MAX(sort_key)` allocation is an index seek. The leftmost
`user_id` serves every by-owner scan, so no single-column index is added.

No DDL at startup. A fresh instance gets the table from bootstrap's `create_all`; an
existing one reports `memos` as missing (and `/api/health` `schema: "missing"`) until an
administrator presses **Create** (FEAT-005).

### D11 — Service modules and their one shared value (planner decision)

- `services/memos.py` owns writes and the one-level list: the **`Memo`** frozen value (the
  row minus `user_id`, with `scope_id` `None` for a user-level note), a pure row-to-value
  mapper, and `create_memo`, `list_memos`, `update_memo`, `delete_memo`. It checks target
  levels with its own owner-scoped selects against the schema Tables and imports no
  `app.services` module.
- `services/memo_chain.py` owns R2 and R3's derivation: `resolve_chain`, its level value,
  and `memo_reach`. It does its own owner-scoped session read and its own memo SELECT.
- **One narrow exception to the "services never import each other" rule (011 D11, 012
  D11), taken deliberately:** `memo_chain.py` imports **only** `Memo` and the pure mapper
  from `services/memos.py`. Both return the same row shape and the router answers both
  with one response model. Two value types for one row would drift. The rule's reason
  (010 D6: a service operation owns its transaction) concerns **operations**, and
  `memo_chain.py` still calls no function that takes a connection. `003`'s source test
  pins the import to those two names.

### D12 — Errors (orchestrator decision)

- **`MemoNotFoundError`**: code `memo_not_found`, **404**, empty `detail`, a fixed
  non-empty default message (the subclass-default pattern of 011 / 012). It answers "no
  such memo" and "another user's memo" alike (R5). The sibling of `session_not_found`.
- A target level that is missing or another user's answers that level's existing code
  (`character_not_found` / `setup_not_found` / `session_not_found`). Each code names what
  the request addressed; no new code for the same condition.
- Validation failures (blank body, missing `scope_id`, unknown scope) are FastAPI's own
  422 and add no domain code.
- Check order inside create: target level, then sort-key allocation, then id minting. A
  refusal inserts nothing and mints nothing.

### D13 — The new-note lifecycle in the UI (planner decision)

"New note" opens **one unsaved new note per level** at the end of that level's list: an
empty editor labelled "Note". While it exists (unsaved or saving), "New note" in that
group is disabled. When focus leaves it:

- blank → it is dropped, no request (D2);
- non-blank → `POST /api/memos`; on 201 the returned row is appended to the level and the
  new note is gone; text typed during the request is kept as that note's editor text, so
  it saves on its next blur; on failure the text stays and "Could not save the note."
  shows under it.

The unsaved new note shows **no flag controls and no reach line**: those act on a stored
row and there is none yet (absent, not disabled, `workspace-shell.md`'s precedent). A
saved new note shows the searchable reach (US-053). Moving focus into the new editor on
"New note" (`workspace-shell.md` "focus lands in the empty body") needs a focus hook that
`shared/MarkdownEditor` does not expose and 015 may not add: deferred to `016`, recorded
in `outcome.md`.

### D14 — Icons and labels for the two flags (planner decision; closes `ui-conventions.md`'s enabled/disabled `_TBD:` provisionally)

- **Forced:** `IconPin` (the icon table's row), one icon whose state is shown by the
  wrapping button's `color` (coloured while forced, default otherwise) and by its label:
  **"Force note"** / **"Stop forcing note"**.
- **Enabled:** `IconCircleCheck` while enabled, `IconCircleOff` while disabled (the
  mockup's "circle with a slash" for disabled), labels **"Disable note"** / **"Enable
  note"**. A two-icon swap, because the mockup swaps the glyph.
- Labels name the **action**, so the accessible name always tells the state too: a
  disabled, forced note shows "Enable note" and "Stop forcing note".
- A disabled note's body renders **dimmed and struck through** while its forced control
  stays visible (`workspace-shell.md`), using Mantine props only (no stylesheet).
- `outcome.md` asks the architect to record the enabled glyph pair, or to replace it.

### D15 — Body validation (orchestrator decision; verbatim storage chosen here)

`body` must be non-blank (empty or whitespace only → 422) on POST and on a PATCH that
supplies it. It is stored **verbatim**, not trimmed: markdown whitespace is content, and
012 D9 stores text verbatim for the same reason. No maximum length: nothing in
`docs/product/` bounds a note. The frontend uses JavaScript `trim` for "blank", which
differs from the server's only on rare code points. A disagreement at worst produces a 422
shown as "Could not save the note.".

### D16 — Frontend state shape (planner decision)

- **`MemoLevelState`** (`006`): one level. It holds the scope and scope id, the load
  status, the notes in server order, each note's editor text, the unsaved new note, and
  per-note failure and pending-toggle bookkeeping. One shared type for the session
  screen's four groups and the character page's one (D1).
- **`MemoChainState`** (`008`): the session's chain. It holds the load status and the
  `MemoLevelState`s it populated from the chain response, in server order. Each group
  mutates its own level state, and nothing is re-read after a mutation.
- The two mounts never share an instance: the character page's level and the session
  screen's character level are separate states over the same rows, each loaded on mount.
  016's wall will face the same question; `outcome.md` notes it.

### D17 — Nine steps

Backend in four: table + error + models; the memos service; the chain service with the
reach twin (split from the memos service because together they exceed 200 LoC, and R2 is
one subject); the router. Frontend in five: the API module with the reach helper; the
level state; the shared level group; the chain state with its section and the session
screen hook; the character page section with its hook. The suggested nine are kept.

## Step map

| Step | Subject | Est. LoC | Depends on |
|------|---------|----------|------------|
| 001 | `memos` Table, `MemoNotFoundError`, `models/memos.py` | ~130 | committed schema Tables |
| 002 | `services/memos.py` — `Memo` value, create / list / update / delete | ~170 | 001 |
| 003 | `services/memo_chain.py` — `resolve_chain`, `memo_reach` | ~90 | 001, 002 |
| 004 | `routers/memos.py` + `main.py` registration | ~115 | 001, 002, 003; 009 / 010 / 011 `001`–`003` delivered |
| 005 | `app/memosApi.ts` + `app/memoReach.ts` | ~100 | 004 (wire contract; tests stub `fetch`) |
| 006 | `app/memoLevelState.ts` | ~170 | 005 |
| 007 | `app/MemoLevelGroup.tsx` | ~160 | 005, 006 |
| 008 | `app/memoChainState.ts` + `app/MemoChainSection.tsx` + `SessionScreen.tsx` hook | ~130 | 005, 006, 007; 011 `009` delivered |
| 009 | `app/CharacterNotesSection.tsx` + `CharacterScreen.tsx` hook | ~55 | 006, 007; 009 / 010 / 011 `008` delivered |

`002` and `003` are ordered (`003` imports `002`'s value). `008` and `009` are independent
of each other.

## Test conventions

Inherited from 011 `context.md` "Test conventions" (backend paragraph: pytest from
`backend/`, no shared fixtures added, `conftest.py` untouched, schema from
`schema.metadata.create_all` on a file-local engine, per-file `application` / `client`
fixtures overriding `get_settings`, a file-local `_insert_user`, login through
`POST /api/auth/login`, two users for isolation; frontend paragraph: Vitest,
`globals: false`, `tests/` mirrors `src/`, `fetch` stubbed per file with `vi.stubGlobal`
and file-local helpers, `render(<AppProviders>…)`, `MemoryRouter` where routed, assertions
on rendered behaviour only, and the per-file `vi.mock` of `src/shared/MarkdownEditor` as a
labelled `<textarea>` as in `tests/app/SetupsSection.test.tsx`). Additions for 015:

- **Test names.** Backend: `test_<behavior>__S015_<SSS>_DoD<n>`. Frontend: each `it` title
  ends **`— DoD-N`** of its own step.
- **FK chain.** `memos` has a FK to `users` only. Service tests raw-insert users,
  characters, setups and sessions (their committed columns) to give targets real ids, and
  raw-insert `memos` rows where a DoD needs a precise state (another user's note, chosen
  `sort_key` values). Router tests create characters, setups and sessions through their
  routes.
- **Stubs by exact path, query and method.** `/api/memos`, `/api/memos?scope=…`,
  `/api/memos/<id>`, `/api/sessions/<id>`, `/api/sessions/<id>/memo-chain` and the stream's
  `/api/sessions/<id>/…` paths share prefixes. A stub or request log keys on the exact
  pathname plus query string plus method, never a prefix.
- **Payload builders** are file-local: a `Memo` with all nine keys, string ids
  (`"7250000000000000201"` style), `scope_id` null for user-level notes.
- **Expected values come from this plan**: the strings table, the reach table in R3, D4's
  allocation rule. Never call `memoReach` / `memo_reach` to compute an expectation.
- **Blur.** With the `MarkdownEditor` mock, the editor is a `<textarea>` labelled "Note".
  Focus loss is `fireEvent.blur` on it (React's `onBlur` bubbles from it to a wrapping
  element). Typing is `fireEvent.change`.
- **Scoping.** Group assertions use `within(getByRole("region", { name: "<group>" }))`,
  then `getAllByRole("listitem")` for notes. The session screen's main region also holds
  011's header and, when 013 has landed, the stream; the character page also holds the
  "Setups" and "Sessions" regions.
- **Timestamps** are asserted by fixed-width shape and by equality / non-decrease, never by
  exact value.

## Vocabulary

| Term | Means here |
|---|---|
| **note** / **memo** | one `memos` row; the product's and the schema's word for the same thing |
| **level** | one of `user`, `character`, `setup`, `session`; stored as `scope` with its `scope_id` |
| **target** | the level row a note is created at or listed for: the caller (user), or a character, setup or session row of the caller |
| **chain** | a session's notes across its levels, in the fixed order user, character, setup (when present), session (R2) |
| **reach** | forced / searchable / disabled, derived from the two flags with `is_enabled` first (R3) |
| **blank** | empty or whitespace only |
| **new note** | the unsaved editor "New note" opens; not a row until its first non-blank save (D13) |
| **editor text** | what a note's editor currently holds; differs from the note's `body` until saved |
| **flush** | saving every changed note and a non-blank new note when a group unmounts (D5) |
| **apply a row** | replace the held note with the returned one, if its `updated_at` is not older (D5) |
