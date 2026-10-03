# Feature 016 — Note wall · feature-wide context

## What this feature is

Puts the session's notes beside the stream. The **note wall** is part of the session
screen: a flyout over the stream that can be **pinned** to become a real column. The pin
survives a reload; merely being open does not. With no session open the wall does not
exist. The wall holds 015's chain of level groups (user → character → setup → session).
In those groups notes are edited in place and saved on blur (015), a new note opens **at
the top** of its level with focus in its body, and saved notes are **reordered within
their level** by dragging or from the keyboard. A note can never be dropped into another
level. Reordering rewrites one level's `sort_key`s on the server through a new route.

The agreed boundary is `brief.md` in this folder (Definition, Scope In/Out). It is **not**
widened, except by the three user decisions U1–U3 the user explicitly asked for (D5, D7,
D8, D9 below). Out stays out: what a note does to the model's context (`020`), finding a
note (`029`), the character page's notes grid (`018`), and any collapsing, filtering or
search inside the wall.

"Note" and "memo" mean the same row (015 `context.md`).

## Product ids

`FEAT-012` via **UC-075**, **UC-076**; `FEAT-020` via **UC-072**.

| Criterion | Where it lands |
|---|---|
| US-094.AC-1 (opening the wall shows it over the stream) | `005` (floating mode), `006` ("Open notes" on the session screen) |
| US-094.AC-2 (a pinned wall is still pinned after a reload) | `005` (pin writes `wallPinned`; state initialised from the record), `006` (remount with the same storage) |
| US-095.AC-1 (no session → the wall is absent, not empty, not disabled) | `006` (the wall exists only in `SessionScreen`'s ready render; every other route and state renders none) |
| US-102.AC-1 (reordered forced notes enter the prompt in the new order) | **partially.** 016 delivers the persisted order: `001` (reorder route rewrites `sort_key`), `002`–`004` (the reorder gesture and its request). The prompt side is `020`'s. Cited forward, never faked |
| US-103.AC-1 (forced notes ordered user, character, setup, session in the prompt) | **not here.** It is `020`'s. 016 keeps the wall's level order fixed (015 `008`, unchanged) |
| US-103.AC-2 (a note dragged toward another level stays at its level) | `004` (the drop logic refuses a cross-level drop: no state change, no request), `001` (the route cannot express a cross-level move: one request = one level; a foreign id is a 409) |
| US-104.AC-1 (a note on the wall is edited in place and saved on blur) | 015 `006`/`007` built it; `006` here mounts it in the wall. `003` keeps it intact while making the card a drag surface |
| US-101.AC-1/AC-2, US-053.AC-1, US-119.AC-1 | 015's, unchanged. Cited as context: the cards keep 015's two flag controls, reach line and single body |

UC-072 steps 1–5 are realised by `005` (modes, pin, dismiss) and `006` (the open
control and the mount). UC-075 is 015's flag controls shown on the wall (`006`). UC-076
is `001`–`004`.

**Not delivered here. Recorded as forward notes, never faked with stand-in tests:**

- **US-102.AC-1 / US-103.AC-1's prompt half**: `020.context-assembly` selects forced
  notes in level order, then `sort_key, id` within a level (015 `outcome.md`). D5 below
  changes **which** note is first in a level for a new note; `outcome.md` flags it.
- Finding a note: `029`. The character page's card grid: `018`. `018` turns on
  reordering for the character page by passing `003`'s opt-in prop (D8).

## Build prerequisites

Built: 001..010. **011**: `011.rp-sessions/status.md` records all nine steps `done` /
`PASS` (2026-10-02), including `009` (`SessionScreen.tsx`, `sessionScreenState.ts`).
**012..015 are planned, not built**; there is **no memos source** today. 016 is built
**after 011, 013 and 015 are delivered**. It binds to 013's and 015's step-file prose,
cited by step number (they have no frozen `## Skeleton` yet), and to 011's frozen
`## Skeleton` → Step 009.

| Step | Needs delivered first | Why |
|---|---|---|
| `001` | 015 `001`–`004` | edits `models/memos.py`, `services/memos.py`, `routers/memos.py`, `errors.py` and their 015 tests |
| `002` | 015 `005`, `006`; 016 `001` (wire only — tests stub `fetch`) | edits `memosApi.ts`, `memoLevelState.ts` and their 015 tests |
| `003` | 015 `007`; 016 `002` | edits `MemoLevelGroup.tsx` and its 015 test; reads `002`'s reorder fields |
| `004` | 015 `008`; 016 `002`, `003` | edits `MemoChainSection.tsx` and its 015 test |
| `005` | 008 (built: `workspaceLayout.ts`, `shellState.ts`, `shell.css`, `tests/stylesheets.test.ts`) | new wall state and layout component; `shell.css` rules |
| `006` | 011 `009`, 013 `007`, 015 `008`; 016 `004`, `005` | edits `SessionScreen.tsx` (011 → 013 `007` → 015 `008`) and `App.tsx`; amends their tests |

## Built state this feature reads

- `frontend/src/app/workspaceLayout.ts`: `WorkspaceLayout` (`navCollapsed`,
  `wallPinned`), `LayoutStorage` (`getItem`, `setItem`), `WORKSPACE_LAYOUT_KEY`
  (`"rphelper.workspace-layout"`), `DEFAULT_WORKSPACE_LAYOUT` (both false),
  `readWorkspaceLayout(storage | null)` (total, never throws),
  `writeWorkspaceLayout(storage | null, patch)` (merge over a fresh total read; errors
  swallowed). `wallPinned` already round-trips and is tested
  (`tests/app/workspaceLayout.test.ts`); nothing reads or writes it yet. **No change to
  this module.**
- `frontend/src/app/shellState.ts`: `NARROW_VIEWPORT_QUERY = "(width < 820px)"`,
  `createShellState(storage)`, `shellClassName`, `browserLayoutStorage()`. The pattern
  016's wall state mirrors. **Not edited.**
- `frontend/src/app/WorkspaceShell.tsx`: renders `.app` with exactly two children
  (`nav.app-nav`, `main.app-main`), and takes `narrow` from
  `useMediaQuery(NARROW_VIEWPORT_QUERY, false, { getInitialValueInEffect: false })`.
  **Not edited.** The shell grid stays two columns (D1).
- `frontend/src/app/App.tsx`: flat `<Routes>` inside `WorkspaceShell`; holds the
  `storage` it gives `WorkspaceShell`; `/sessions/:id` →
  `<SessionRoute characters={characters} />`.
- 011 frozen (`011.rp-sessions/status.md` `## Skeleton` → Step 009):
  `SessionScreenProps = { sessionId: string; characters: CharactersState }`,
  `SessionRouteProps = { characters: CharactersState }`; `SessionRoute` renders
  `<SessionScreen key={sessionId} …/>` from `useParams().id ?? ""`. **`006` re-freezes
  both props types** (D2).
- `frontend/src/shell.css` (65 lines): `.app`, `.app.nav-collapsed`, `.app-nav`,
  `.app-main` (`grid-column: 2; min-width: 0; overflow: auto`), and one
  `@media (width < 820px)` block.
- `frontend/tests/stylesheets.test.ts`: exactly two stylesheets
  (`["global.css", "shell.css"]`); `ALLOWED_SELECTORS = [".app", ".app.nav-collapsed",
  ".app-nav", ".app-main", ".app.nav-overlay-open .app-nav"]`; `shell.css` declares no
  colour, no font or typography, no import, no `@font-face`; its media query string is
  byte-identical with `NARROW_VIEWPORT_QUERY`. `frontend/tests/conventions.test.ts`:
  `@mantine/notifications` is imported only by `shared/notifyFailure.ts`.
- `frontend/src/shared/MarkdownEditor.tsx`: props `label`, `value`, `onChange(markdown)`,
  `readOnly?`; no focus hook. `shared/IconButton.tsx`: `icon`, `label`, `onClick`,
  `disabled?`, `color?`, `sizeVariant?`. `shared/api.ts`: `apiGet` / `apiPost` /
  `apiPatch` / `apiDelete` (path, optional body, optional signal; non-2xx → `ApiError`;
  204 → `undefined`). **No `apiPut`** (D12).
- `frontend/package.json`: **no `@dnd-kit/*`**. Mantine 7.17.8, `@tabler/icons-react`
  ^3.40, mobx ^6.16, react ^19.3, react-router-dom ^7.18, tiptap ^2.27, vitest ^5, jsdom,
  `@testing-library/react` ^16, `user-event` ^14.
- Backend `main.py` registers health, bootstrap, auth, admin_users, admin_llm, admin_db,
  characters, setups, sessions, and memos last (015 `004`). **016 adds no router**: the
  reorder route joins `routers/memos.py`, so `main.py` is not edited.
- 015 contracts (planned, bound by prose): `services/memos.py` (`Memo`, the row mapper,
  `create_memo`, `list_memos`, `update_memo`, `delete_memo`; connection first, `user_id`
  required positional, owner scope in SQL); `routers/memos.py` (five routes);
  `models/memos.py` (scope literal, `MemoResponse`, `MemoListResponse`,
  `CreateMemoRequest`, `UpdateMemoRequest`, …); `app/memosApi.ts`; `app/memoReach.ts`;
  `app/memoLevelState.ts` (`MemoLevelState`, `saveNewNote`, `applyMemoRow`,
  `flushMemoLevel`, …); `app/MemoLevelGroup.tsx` (props `state`, `title`,
  `headingOrder`, `onRetry`); `app/memoChainState.ts`; `app/MemoChainSection.tsx`
  (region "Notes", the four groups); `app/CharacterNotesSection.tsx`.

## Wire contract — what 016 changes

015's `context.md` "Wire contract — memos" stands, with these changes:

**Create allocation (D5).** A new note's `sort_key` is one **less** than the smallest
`sort_key` among the caller's notes at that `(scope, scope_id)`, or 0 when there are none.
So a level's notes list **newest first** until reordered. `sort_key` is a **signed**
integer on the wire (a JSON number, possibly negative). It is no longer "a small
non-negative integer".

**New route (D6):**

| Route | Body | Answers |
|---|---|---|
| `PUT /api/memos/order` | `{ scope, scope_id?, memo_ids: ["<decimal string>", …] }` | 200 `{ memos: [Memo…] }`: the level's notes in the given order, `sort_key` 0..n-1, every other field as stored |

Request rules: `scope` and `scope_id` follow `POST /api/memos` exactly (`scope_id`
required for a non-user scope, ignored for `"user"`; unknown scope → 422). `memo_ids` is
required and is a JSON array of decimal strings. It may be empty only for an empty level.
A non-numeric id → 422. Unknown body keys are ignored.

| Code | Status | When |
|---|---|---|
| `character_not_found` / `setup_not_found` / `session_not_found` | 404 | the target level is missing or another user's (015's codes) |
| `memo_order_mismatch` | **409** (**new**) | `memo_ids` is not exactly the set of the caller's notes at that level: one missing, an extra one (another level's, another user's, nobody's), or a duplicate. The client's view is stale. `detail` empty |
| — | 422 | missing / non-array `memo_ids`, a non-numeric id, unknown scope, non-user scope without `scope_id` |
| `not_authenticated` | 401 | no login cookie |

A refusal writes nothing. One request addresses one level, so a cross-level move cannot
be expressed (US-103.AC-2).

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

- `docs/architecture/workspace-shell.md`: **"The wall has two modes"** (floating:
  absolute, anchored to the stream's right edge, transform + shadow, animated; pinned: a
  real column `minmax(0,1fr) auto`, no shadow, not animated; the pin survives a reload,
  open does not; no session → no wall; below 820px pinned reverts to floating);
  **"Geometry"** (floating `min(320px, 84vw)`, pinned `320px`, threshold `820px`);
  **"Layout persistence"** (one record, write on the toggle, merge over a fresh read);
  **"The wall's contents"** and **"`@dnd-kit` is finally used"** (cross-level refused in
  the drop handler; keyboard sensor required; a note being edited is not draggable);
  "The character page" (same components, different arrangement).
- `docs/architecture/ui-conventions.md`: the workspace icon table (Open the note wall
  `_TBD:`; Pin / unpin `IconPin` with an active state; Dismiss `IconX`; the pin-glyph
  clash `_TBD:`); "Accessibility floor" (keyboard path for reordering); "Async feedback"
  (no success toast; a failure with a place of its own is not a notification);
  **"Mutations are never optimistic"** (D7 is a recorded exception).
- `docs/architecture/frontend-structure.md`: "Routing inside the `app` entry"
  (`/sessions/:id` is tree | stream | wall; `/` has no wall); "State — MobX 6" (four
  rules); the `@dnd-kit` bullet under "Bundle-level constraints"; "The two stylesheets"
  (`shell.css` holds workspace layout only); "Ids are strings".
- `docs/architecture/data-model.md` **"### `memos`"** (`sort_key` mutable, scoped within
  `(scope, scope_id)`, no unique constraint).
- `docs/architecture/domain-rules.md`: **R2** (the chain's fixed level order), **R3**
  ("Order is a third, independent thing"), **R5** (owner scope in SQL).
- `docs/architecture/backend-structure.md`: "Routers versus services", "The error model"
  / "The per-code status record", "The logging call site".
- Product: `use-cases/FEAT-012.memos.md` (UC-075, UC-076),
  `use-cases/FEAT-020.workspace-shell.md` (UC-072), `stories/FEAT-012.memos.md`
  (US-102, US-103, US-104), `stories/FEAT-020.workspace-shell.md` (US-094, US-095).

Cited, never copied.

## Files this feature touches

```
backend/
  app/errors.py                  # + MemoOrderMismatchError                          (001)
  app/models/memos.py            # + reorder request model                           (001)
  app/services/memos.py          # create allocation → MIN-1; + reorder_memos        (001)
  app/routers/memos.py           # + PUT /api/memos/order                            (001)
  tests/test_memos_service.py, tests/test_memos_models.py,
  tests/test_memos_router.py     # 016 additions + amended 015 assertions            (001)
frontend/
  src/shared/api.ts              # + apiPut                                          (002)
  src/app/memosApi.ts            # + reorderMemos                                    (002)
  src/app/memoLevelState.ts      # + reorder effect and its fields; new note prepends (002)
  package.json, package-lock.json  # + @dnd-kit/core, /sortable, /utilities         (003)
  src/shared/MarkdownEditor.tsx  # + optional autoFocus                              (003)
  src/app/MemoLevelGroup.tsx     # new note on top + autofocus; opt-in sortable cards (003)
  src/app/memoReorder.ts         # NEW — pure drop decision + the drop effect        (004)
  src/app/MemoChainSection.tsx   # DndContext + sensors; groups reorderable          (004)
  src/app/noteWallState.ts       # NEW — the wall's data class + derivations/actions (005)
  src/app/NoteWallLayout.tsx     # NEW — stream column + the wall aside              (005)
  src/shell.css                  # + the session screen / wall layout rules          (005)
  src/app/SessionScreen.tsx      # wall layout in the ready render; storage prop     (006)
  src/app/App.tsx                # passes storage to SessionRoute                    (006)
  tests/shared/api.test.ts, tests/app/memosApi.test.ts,
  tests/app/memoLevelState.test.ts                                                   (002)
  tests/app/MemoLevelGroup.test.tsx                                                  (003)
  tests/app/memoReorder.test.ts, tests/app/MemoChainSection.test.tsx                 (004)
  tests/app/noteWallState.test.ts, tests/app/NoteWallLayout.test.tsx,
  tests/stylesheets.test.ts                                                          (005)
  tests/app/SessionScreen.test.tsx, tests/app/App.test.tsx,
  tests/app/WorkspaceShell.test.tsx                                                  (006)
```

**Not touched. A step that touches one is out of scope:**

- Backend: `app/main.py` (no new router), `db/schema.py` (`sort_key` is already a signed
  `Integer`; no column, index or constraint changes), `services/memo_chain.py`, every
  009 / 010 / 011 / 012 module, `dependencies.py`, `ids.py`, `models/ids.py`,
  `db/engine.py`, `backend/tests/conftest.py`, `tests/test_memo_chain_service.py` (its
  orders come from raw-inserted `sort_key`s, 015 `003` DoD-1), `tests/test_db_schema.py`.
  No new Python dependency.
- Frontend: `WorkspaceShell.tsx`, `shellState.ts`, `workspaceLayout.ts`, `CharacterTree.tsx`,
  `UserMenu.tsx`, `AppBoot.tsx`, `main.tsx`, `sessionScreenState.ts`, `sessionsApi.ts`,
  `sessionsState.ts`, every 013 / 014 module (`SessionStream.tsx`, `streamState.ts`, …),
  `memoReach.ts`, `memoChainState.ts`, **`CharacterNotesSection.tsx`**,
  **`CharacterScreen.tsx`**, `shared/IconButton.tsx` (not widened), `shared/notifyFailure.ts`,
  `shared/AppProviders.tsx`, `src/admin/*`, `src/global.css`, `vite.config.ts`,
  `tests/setup.ts`, `tests/conventions.test.ts`, `tests/ids-are-strings.test.ts`,
  `tests/app/workspaceLayout.test.ts`, `tests/app/CharacterNotesSection.test.tsx`,
  `tests/app/CharacterScreen.test.tsx`, `tests/entries.test.tsx` (the `/sessions/abc123`
  clause already answers the chain since 015 `008`; the wall issues no new request), and
  every other test file not listed above.
- No third stylesheet, no `.css` beside a component, no Tailwind or CSS modules.

## Cross-cutting constraints every step holds

**Owner scope lives in SQL (R5).** The reorder's target check, its set read and every
`UPDATE` carry `memos.user_id = <caller>` (and the parent table's own `user_id` for the
level check). The amended allocation's `MIN(sort_key)` read does too. Nothing is fetched
and filtered in Python.

**Routers own HTTP; services own SQL.** The reorder handler holds no SQL. The service
raises domain errors only. 015's D11 module rules are unchanged.

**No memo body in a log line or an error `detail`.** `memo_order_mismatch` carries an
empty `detail`. It never lists which ids mismatched: ids of another user's notes would
leak through it.

**Ids are strings in every frontend file and payload.** `memo_ids` crosses as decimal
strings. dnd-kit's identifiers are memo id strings, read back with `String(…)`, never
parsed. No client-side sort on an id; the order is the user's arrangement or the
server's.

**Pure data contracts.** `NoteWallState` and the new `MemoLevelState` fields are
observable fields only. Every derivation and effect is a free function taking the state
first. Effects `runInAction` their writes and never reject. One instance per mount via
`useState(() => …)`, passed as a prop, with no React context. Every reader is an
`observer`. A card's "my editor has focus" flag is component-local view state, like the
modal-open flag (`ui-conventions.md` "Modal open/target flags").

**Never optimistic, with one recorded exception.** Everything stays 015's D5 except the
reorder (D7): the dropped order shows immediately and reverts on failure.

**Every icon-only control goes through `shared/IconButton`.** Tests find controls by
accessible name. The strings table below is the contract.

**No notification anywhere in 016.** Every failure has a place of its own.
`notifyFailure` is not imported.

**TypeScript only.** No `.js` / `.jsx` / `.mjs` / `.cjs`. Every new file is `.ts` /
`.tsx`.

## UI strings — the contract tests bind to

015's strings table (015 `context.md`) is unchanged and still binds. Additions:

| Where | String | Role / element |
|---|---|---|
| Session header | **"Open notes"** | `IconButton` with `IconNotes`; present **only while the wall is not visible** (`006`) |
| The wall | complementary landmark named **"Note wall"** | an `aside` (`005`). It holds 015's region "Notes" with its four (or three) groups |
| Wall header — pin | **"Pin notes"** while not pinned; **"Unpin notes"** while pinned | `IconButton` with `IconPin`, given a `color` while pinned (the active state) (`005`) |
| Wall header — dismiss | **"Close notes"** | `IconButton` with `IconX` (`005`) |
| A sortable note card | accessible name **"Note <n> of <total>"** (1-based position among the level's saved notes) | the note's `listitem`, focusable, in a reorderable group only (`003`) |
| Reorder failure | **"Could not reorder the notes."** | inline text in that level's group, never a notification (`002` sets it, `003` renders it) |

## Decisions — settled, with their reasoning

"015 Dn" refer to `docs/plans/015.memos/context.md`. U1–U3 are user decisions given for
this feature; O1–O8 are orchestrator decisions. Both are binding.

### D1 — The wall lives in the session screen, not in the shell (O1)

The wall is part of `SessionScreen`'s **ready** render and never part of
`WorkspaceShell`. Loading, not-found and failed render no wall, and so does every other
route. US-095 then holds by construction rather than by a flag. `WorkspaceShell`'s grid
stays two columns (`nav`, `main`). Inside `main`, the session screen's root becomes the
wall's positioning context. It is a grid of a **stream column** (011's header plus 013's
`SessionStream`) and the **wall**:

- **pinned (and not narrow)**: the root's columns are `minmax(0, 1fr) auto` and the wall
  is a 320px column with no shadow and no animation;
- **floating**: the root has one column, and the wall is `position: absolute` against the
  root's right edge (the stream's right edge), width `min(320px, 84vw)`, slid in and out
  with `transform: translateX(…)` (animated), with a shadow while shown.

The stream column scrolls on its own (`overflow: auto`) and the root clips overflow. That
keeps the floating wall anchored while the stream scrolls, and stops a closed wall
(translated off to the right) from adding a horizontal scrollbar. The layout rules live in
`shell.css` (D11). The geometry numbers are `workspace-shell.md`'s.

Why not in the shell: the shell has no session. Hoisting the wall there would need a
session-open signal threaded upward plus a second place that decides US-095.
`workspace-shell.md`'s "a real column of the centre grid" is realised as the session
screen's own grid inside the shell's centre column. `outcome.md` records this.

### D2 — The wall's state and its modes (O2; one interpretation flagged)

`app/noteWallState.ts`: a data class `NoteWallState` with two observable fields:

- `pinned`: initialised from `readWorkspaceLayout(storage).wallPinned`;
- `open`: not persisted, starts `false`.

`narrow` is not state. The screen reads it with
`useMediaQuery(NARROW_VIEWPORT_QUERY, false, { getInitialValueInEffect: false })`, as
`WorkspaceShell` does, and passes it to every derivation.

| | not narrow | narrow (`< 820px`) |
|---|---|---|
| **effective mode** | `pinned` → pinned column; else floating | always floating |
| **visible** | `pinned \|\| open` | `open` |

Actions (synchronous MobX actions; no request):

- **open**: `open = true`. Never writes the layout record.
- **toggle pin**: from unpinned, `pinned = true` and write `{ wallPinned: true }`, with
  `open` unchanged. From pinned, `pinned = false`, `open = true` (unpinning leaves the
  wall visible as a floating flyout) and write `{ wallPinned: false }`.
- **dismiss**: `open = false`. When the wall is **effectively pinned** (pinned and not
  narrow), it also sets `pinned = false` and writes `{ wallPinned: false }`. A pinned wall
  stays until dismissed (UC-072 steps 4–5), and once dismissed it is gone.

**Interpretation, flagged in the hand-back:** at narrow width a pinned wall is shown
floating, and its stored pin must stay so that widening restores the column (O2). So
**dismissing it there only closes it and does not unpin**. Otherwise a quick glance-close
on a small window would silently erase the preference.

The record is written only by the pin toggle and by a dismiss that unpins, which is
`workspace-shell.md`'s "written on the toggle". The state lives per `SessionScreen`
mount, and `SessionRoute` keys the screen by session id. So `open` resets when the session
changes, and `pinned` is re-read from the record. `storage` reaches the screen as a prop:
`App` already holds it, passes it to `SessionRoute`, and `SessionRoute` passes it to
`SessionScreen`. **This re-freezes 011's frozen `SessionScreenProps` and
`SessionRouteProps`**: each gains a required `storage` (the `LayoutStorage | null` `App`
holds). The skeleton agent must re-freeze both. Required rather than optional matches
011's "one prop, no optional branch".

### D3 — Mounted while closed (O3)

The wall and its contents (`MemoChainSection`) mount **once per ready session screen**
and stay mounted while the floating wall is closed. Opening, closing, pinning and
unpinning change classes and attributes only. The wall element keeps the same position in
the React tree in every mode, so it is never remounted. The chain therefore loads once
per session mount, and an unsaved edit survives a close.

A closed wall is slid out **and** removed from the accessibility tree and the tab order.
It carries both the `inert` attribute and `aria-hidden="true"`. `inert` takes it out of
focus and interaction in browsers. `aria-hidden` is what jsdom and Testing Library observe:
a closed wall is not found by role without `{ hidden: true }`. The `hidden` attribute is
not used, because it would `display: none` the wall and kill the slide animation.

### D4 — Contents: 015's chain section, moved; landmark "Note wall"; separate chain state (O4)

015 `008`'s `MemoChainSection` (region "Notes", groups "Your notes" / "Character notes" /
"Setup notes" / "Session notes" in fixed order, setup absent with no setup) **moves**
from the session screen's main column into the wall. It is otherwise unchanged apart from
`004`'s drag wiring. Level headers are the only structure: no collapsing, filtering or
search (brief Out).

The wall's landmark is a complementary `aside` named **"Note wall"**, not "Notes". The
region inside it is already named "Notes" (015 `008`, unchanged). Two landmarks with one
name would make both ambiguous to assistive technology and to tests. "Note wall" is the
product's own term (US-094, US-095).

**The answer to 015 `outcome.md`'s open question.** The wall's chain state is
**separate** from the character page's level state. The two are never on screen together
(US-095, and the character page is a different route), so there is nothing to keep in
sync while both are visible. Each loads its rows on mount, so each shows the server's
current rows when it appears. `outcome.md` records it.

### D5 — A new note goes on top and stays first: the D4 amendment (U3)

015 D4 is amended. Create allocation becomes **`COALESCE(MIN(sort_key), 1) - 1`** over
the caller's notes at the same `(scope, scope_id)`, computed inside the create
transaction. A level's first note is still 0; later ones are -1, -2, …. A saved new note
therefore lists **first**, and stays first in the persisted order until it is reordered.
`sort_key` becomes a **signed** integer. The column is already a plain signed `Integer`,
so there is no schema change. Lists and the chain still order by `sort_key, id`. The
reorder route renormalises a level to 0..n-1 (D6), and later creates go below the minimum
again. Gaps and negatives are harmless.

Frontend: the saved new note is **prepended** to its level (`002`), and `MemoLevelGroup`
renders the new-note listitem **first** (`003`). That matches where the server will list
it, so the client never re-sorts.

**Consequence flagged for `/product-spec`** (`outcome.md`): a newly created note is first
in its level, so a newly created and then forced note enters the prompt **ahead** of the
level's older forced notes until it is reordered (US-102). This was a deliberate user
choice, recorded so it is not mistaken for a bug.

**015 assertions this amends** (each amending step names them again):

| 015 item | Was | Becomes | Amended in |
|---|---|---|---|
| `002` DoD-4 (`test_memos_service.py`) | 0, 1, 2; next after {2, 5} is 6; after deleting the highest, max + 1 | 0, -1, -2; next after {2, 5} is 1; after deleting the lowest, remaining min − 1; another user's row (e.g. -40) does not affect it | `001` |
| `004` DoD-14 (`test_memos_router.py`) | creation order, `sort_key` 0, 1, 2; next create 3, listed last | newest first, `sort_key` 0, -1, -2 listed as -2, -1, 0; after deleting the middle, the next create answers -3 and lists first | `001` |
| `006` DoD-10 (`memoLevelState.test.ts`) | the returned row is the **last** entry of `memos` | the **first** entry | `002` |
| `007` DoD-11, DoD-12, DoD-13 (`MemoLevelGroup.test.tsx`) | "New note" adds a **last** listitem; after the 201 the **last** listitem shows the controls | **first** listitem in both | `003` |
| `008` DoD-7, DoD-8, DoD-9 (`SessionScreen.test.tsx`, `App.test.tsx`) | the "Notes" region in the main column after the header, always accessible | inside the "Note wall" landmark, accessible once the wall is open or pinned | `006` |

Assertions that only check "the note is listed" or the first note's `sort_key` 0 (015
`002` DoD-1, `004` DoD-2/DoD-3, `009` DoD-2) still hold and are not amended.

### D6 — The reorder route and service (O5; `updated_at` choice made here)

- **Service**: `services/memos.py` gains `reorder_memos`. It takes the connection, the
  required positional `user_id`, the scope, the scope id and the ordered memo ids. One
  write transaction does:
  1. the target-level check exactly as create does (that level's 404 code);
  2. one owner-scoped read of the caller's note ids at that level;
  3. a check that the given ids are exactly that set with no duplicate, else
     `MemoOrderMismatchError`;
  4. a rewrite of each note's `sort_key` to its index, 0..n-1, in the given order;
  5. a return of the level ordered by `sort_key, id` as `Memo` values.

  A refusal writes nothing.
- **`updated_at` is not moved by a reorder.** Order is the arrangement of a level, not
  the content of a note. Bumping it would stamp every note in the level as "just edited"
  and make the timestamp meaningless. It would also make every in-flight body or flag
  write's response look older than the reorder's rows under 015 D5's apply-a-row rule.
  Body and flags are untouched.
- **Error**: `MemoOrderMismatchError`, code `memo_order_mismatch`, **409**, empty
  `detail`, with a fixed non-empty default message (015 D12's pattern). 409 rather than
  422: the request is well-formed, but it conflicts with the level's current state.
- **Model**: a reorder request model in `models/memos.py`. Unknown keys are ignored.
  `scope` and `scope_id` follow `CreateMemoRequest`'s rules (a non-user scope needs
  `scope_id`). `memo_ids` is a required list of inbound snowflakes.
- **Route**: `PUT /api/memos/order` in `routers/memos.py`, 200, answering 015's
  `MemoListResponse`. For `"user"` a supplied `scope_id` is dropped before the service.
  The handler is declared **before** the `PATCH` / `DELETE /api/memos/{memo_id}`
  handlers in the module. The methods differ, so nothing collides, but declaring the
  literal path first makes that independent of method-matching subtleties.

### D7 — Reorder is optimistic and reverts on failure (U1 — recorded exception)

On a drop, the level shows the new order **immediately**, and the whole level's order is
sent. On success the returned rows are applied. On failure the level reverts to its
pre-drop order and **"Could not reorder the notes."** shows inline in that level's group.
While a reorder is in flight in a level, further drags in that level are disabled, and a
second reorder call there sends nothing.

This is a **deliberate exception** to `ui-conventions.md`'s "Mutations are never
optimistic". The user's reason: a dropped card that snaps back to where it was until the
server answers reads as broken. `outcome.md` asks the architect to record it with that
reason.

Merging with concurrent writes (a body save, a toggle or a create can be in flight in the
same level):

- **success**: the level's order becomes the returned order. Each returned row is applied
  under 015 D5's rule: it replaces the held row only if its `updated_at` is not older,
  otherwise the held row is kept in the returned position. A held note absent from the
  response (created while the reorder was in flight) stays, placed **first** (D5's
  position). A returned row not held (deleted meanwhile) is not inserted;
- **failure**: the notes return to their **pre-drop relative order**, applied to the level
  as it is now. A note created meanwhile stays first, and a note deleted meanwhile stays
  gone. Nothing is resurrected and nothing typed is lost;
- a 409 `memo_order_mismatch` is a failure like any other (same text). The level is not
  refetched.

### D8 — Drag mechanics (O6, U2)

- **Packages**: `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`, added to
  `package.json` and the lockfile in `003`, the first step that imports them. The coder
  resolves current versions compatible with React 19. This is `frontend-structure.md`'s
  one sanctioned `@dnd-kit` use.
- **One `DndContext` over the wall's chain** (in `MemoChainSection`, `004`) and **one
  `SortableContext` per level** (in `MemoLevelGroup`, `003`, vertical list strategy, the
  level's saved note ids in order).
- **Opt-in, no fork.** `MemoLevelGroup` gains an optional `reorderable` prop, false by
  default. Only when it is true do the saved notes render as sortable cards, through a
  thin sortable wrapper around 015's own card markup. When it is false, no dnd-kit hook
  runs and no `DndContext` is needed. `CharacterNotesSection` passes nothing, so the
  character page is unchanged. `018` turns reordering on there.
- **The drop decision is pure.** `memoReorder.ts` takes the levels' ordered note ids, the
  active id and the over id, and returns the level plus its new id order, or nothing when
  the drop is refused. It is refused when: there is no over target; the over note is in a
  **different level** (US-103.AC-2, enforced here and not only in the preview); the
  active and over ids are the same; or an id is unknown. A refused drop changes no state
  and sends no request. A companion effect applies an accepted decision through `002`'s
  reorder effect. `MemoChainSection`'s drag-end handler only calls that effect.
- **Sensors** (`004`): `PointerSensor` with an activation constraint of **distance 6px**,
  so a click edits and only a press-and-move drags (U2). `KeyboardSensor` with
  `sortableKeyboardCoordinates`, which is required (US-102, `ui-conventions.md`
  accessibility floor).
- **The whole card is the drag surface** (U2). The pointer and keyboard listeners sit on
  the note's `listitem`. The card is **focusable** (`tabIndex` 0). It **keeps role
  `listitem`**, so 015's list semantics and tests hold: dnd-kit's default `role="button"`
  is overridden. It carries the accessible name "Note <n> of <total>" and dnd-kit's
  `aria-roledescription` / `aria-describedby`.
- **Keyboard activation only from the card itself.** The card's keydown listener is
  wrapped. It forwards to dnd-kit only when the event's target **is the card element
  itself** (`event.target === event.currentTarget`). A keydown that bubbles up from the
  editor (Space and Enter typed into a note), or from a flag button, is ignored by the
  sensor and reaches its own target unchanged.
- **Not draggable**:
  - a card whose editor **has focus**. The card tracks focus entering and leaving its
    editor area as component-local view state, and passes `disabled` to its sortable
    hook (`workspace-shell.md`: "A note being edited is not draggable");
  - every card in a level whose reorder is **in flight** (D7);
  - the **unsaved new note**, which is never sortable, is not focusable as a card, and
    has no position name.
- **The residual tension, flagged.** `workspace-shell.md` says "a text selection inside
  [a card] must not start a drag". Under U2 that holds for a card whose editor already
  has focus. A press-and-move that begins on the text of an **unfocused** card is a drag
  (U2: "a drag reorders"). `outcome.md` asks the architect to record it.
- **jsdom limits.** jsdom reports zero-size rects, so pointer movement and keyboard
  *movement* cannot be exercised in tests. Keyboard *activation* (Space on a focused card
  fires the context's `onDragStart`) needs no geometry and is tested (`003`). Everything
  else that is decidable is a `[test]`: the pure decision, the effect, the disabled
  conditions and the card's role, focus and name. The physical gestures are
  `[manual/live]`.
- **Announcements** never read a memo id aloud. They name the note by its position in
  its level (`004`, `[manual/live]`).

### D9 — Autofocus on "New note" (U3; closes 015 D13's deferral)

`shared/MarkdownEditor` gains an optional `autoFocus` prop, false by default. When it is
true, the editor puts focus into its body when it mounts. Omitting it changes nothing for
any existing caller. `MemoLevelGroup` passes it true for the new note's editor only. "New
note" mounts that editor at the top of the level (D5), and focus lands in its empty body
(`workspace-shell.md`). This also applies on the character page, which shares the group.
That is the one character-page change U3 implies.

### D10 — Icons and strings (O7)

- **Open the wall**: `IconNotes`, label "Open notes", present only while the wall is not
  visible. This provisionally closes `ui-conventions.md`'s `_TBD:` "Open the note wall";
  `outcome.md` asks the architect to confirm or replace it.
- **Pin toggle**: `IconPin`, "Pin notes" / "Unpin notes". The active state is the
  `IconButton` `color` while pinned (015 D14's forced-control form).
- **Dismiss**: `IconX`, "Close notes".
- The **pin-glyph clash** with 015's forced control (`IconPin` for both) stays the open
  `_TBD:` in `ui-conventions.md`. It is recorded and not resolved.
- All three go through `shared/IconButton`. No notifications. 015's group titles and
  per-note strings are unchanged.

### D11 — `shell.css` additions, and where the narrow revert is decided (O1)

Six new selectors, colourless and typography-free, appended to `shell.css`.
`tests/stylesheets.test.ts`'s `ALLOWED_SELECTORS` is amended in the same step (`005`):

| Selector | Holds |
|---|---|
| `.app-session` | the session screen's root: `position: relative`, a one-column grid `minmax(0, 1fr)`, fills the main column's height, clips overflow |
| `.app-session.wall-pinned` | `grid-template-columns: minmax(0, 1fr) auto` |
| `.app-stream` | the stream column: `min-width: 0`, scrolls on its own |
| `.app-wall` | floating: `position: absolute`, top / right / bottom 0, `width: min(320px, 84vw)`, its own scroll, `transform: translateX(100%)`, a `transform` transition, stacked above the stream |
| `.app-wall.wall-open` | `transform: translateX(0)` |
| `.app-session.wall-pinned .app-wall` | pinned: `position: relative`, `width: 320px`, no transform, no transition |

The wall's **shadow and background are Mantine's** (a `Paper` with `shadow` only while
floating, none while pinned), so `shell.css` declares no colour. The **narrow revert is
decided in TypeScript** (D2's effective mode reads `NARROW_VIEWPORT_QUERY`, the exact
string `shell.css`'s existing media query uses). No wall rule is added under a media
query. One source decides the mode. CSS alone could not express "a pinned wall at narrow
width is shown only when opened". `.app-main` may gain a height or display rule if the
session root needs it to fill the column. No other existing rule changes.

### D12 — `shared/api.ts` gains `apiPut` (planner decision)

The harvest shows the shared client has no PUT helper, and O5 fixes the method as PUT.
`002` adds `apiPut` with `apiPatch`'s exact shape and error mapping (path, optional body,
optional signal; non-2xx → `ApiError`). Adding a verb to the one client keeps "one decode,
in the client" (`frontend-structure.md`). A raw `fetch` in `memosApi.ts` would be a second
decode.

### D13 — Six steps

| Step | Subject | Est. LoC | Depends on |
|------|---------|----------|------------|
| 001 | Backend: allocation → MIN−1, `reorder_memos`, `MemoOrderMismatchError`, reorder model, `PUT /api/memos/order` | ~120 | 015 `001`–`004` |
| 002 | `apiPut`, `reorderMemos`, the level state's optimistic reorder effect, new note prepends | ~90 | 001 (wire), 015 `005`–`006` |
| 003 | dnd-kit deps; `MarkdownEditor` `autoFocus`; `MemoLevelGroup`: new note on top + autofocus, opt-in sortable cards, reorder failure line | ~130 | 002, 015 `007` |
| 004 | `memoReorder.ts` (pure decision + drop effect); `MemoChainSection`: `DndContext`, sensors, groups reorderable | ~90 | 002, 003, 015 `008` |
| 005 | `noteWallState.ts`, `NoteWallLayout.tsx`, `shell.css` rules + stylesheet guard | ~145 | 008 (built) |
| 006 | `SessionScreen` integration ("Open notes", the wall layout, chain moved into the wall, `storage` prop) + `App.tsx` | ~60 | 004, 005; 011 `009`, 013 `007`, 015 `008` |

The backend is one step. The route alone is about 30 lines, below the floor, so it joins
the service it calls. The wall state (about 55 lines) joins its layout component in
`005`. `005` is independent of `001`–`004` and may be built in parallel.

## Test conventions

Inherited from 015 `context.md` "Test conventions": backend file-local fixtures with
`conftest.py` untouched, two users for isolation, router tests creating parents through
their routes; frontend Vitest with `fetch` stubbed per file, stubs keyed by **exact
pathname + query + method**, `render(<AppProviders>…)`, `MemoryRouter` where routed, the
per-file `vi.mock` of `src/shared/MarkdownEditor` as a labelled `<textarea>`, blur via
`fireEvent.blur`, scoping with `within`, expected values from this plan only. Additions
for 016:

- **Test names.** Backend: `test_<behavior>__S016_<SSS>_DoD<n>`. Frontend: each `it`
  title ends **`— DoD-N`** of its own 016 step. An **amended 015 test** is renamed to
  carry the 016 id: backend appends `__S016_<SSS>_DoD<n>` to its 015 name; frontend ends
  its title with the 016 `— DoD-N`, and may name the 015 item earlier in the title.
  Nothing else in an amended test changes beyond what the amending DoD states.
- **`/api/memos/order`** shares a prefix with `/api/memos` and `/api/memos/<id>`. Stubs
  and request logs key on the exact path and method (`PUT`).
- **Request bodies** are asserted by parsing the JSON and comparing whole objects
  (`memo_ids` as an array of strings, in order).
- **Layout storage** is a file-local in-memory `LayoutStorage` fake (`getItem` /
  `setItem`, with writes recorded). A **reload** is unmounting and rendering again with
  the same fake. Writes are asserted by reading the stored JSON under
  `"rphelper.workspace-layout"`, never by calling `readWorkspaceLayout` for the
  expectation.
- **Narrow width**: drive `window.matchMedia` for the query `(width < 820px)` the way
  `tests/app/WorkspaceShell.test.tsx` already does (its harness or file-local stub).
- **A closed wall** is queried with `{ hidden: true }`. "Not accessible" means not found
  by role without it.
- **dnd-kit in jsdom**: render reorderable groups inside a `DndContext` (`003`'s tests
  build their own, with a `KeyboardSensor`; `004`'s use `MemoChainSection`'s). Keyboard
  activation is `fireEvent.keyDown(<card>, { code: "Space", key: " " })` on the focused
  card; the observable is the context's `onDragStart`. Pointer and arrow-key movement are
  not exercised (zero-size rects).
- **The `MarkdownEditor` mock records `autoFocus`** alongside `label` and `value`.
