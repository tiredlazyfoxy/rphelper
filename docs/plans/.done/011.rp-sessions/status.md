# Feature 011 — rp-sessions

| Step | File                              | Status  | Verifier | Date |
|------|-----------------------------------|---------|----------|------|
| 001  | `001.table-errors-models.md`      | done    | PASS     | 2026-10-02 |
| 002  | `002.sessions-service.md`         | done    | PASS     | 2026-10-02 |
| 003  | `003.sessions-router.md`          | done    | PASS     | 2026-10-02 |
| 004  | `004.sessions-api-and-state.md`   | done    | PASS     | 2026-10-02 |
| 005  | `005.tree-display-helpers.md`     | done    | PASS     | 2026-10-02 |
| 006  | `006.tree-session-level.md`       | done    | PASS     | 2026-10-02 |
| 007  | `007.sessions-section-state.md`   | done    | PASS     | 2026-10-02 |
| 008  | `008.sessions-section.md`         | done    | PASS     | 2026-10-02 |
| 009  | `009.session-screen.md`           | done    | PASS     | 2026-10-02 |

## Files Changed

### Step 001 — the sessions table, its two errors and its pydantic models

No change needed — all three files were already in final form from the skeleton freeze, and
were verified against D8, D12 and the Wire contract rather than rewritten.

- `backend/app/db/schema.py` — verified, unchanged. The `sessions` Table literal is declared
  **after** `setups` (registry order `users, auth_sessions, llm_servers, models, characters,
  setups, sessions`) with exactly D8's eight columns in order (`id`, `user_id`,
  `character_id`, `setup_id`, `last_used_at`, `archived_at`, `created_at`, `updated_at`);
  `id` is the primary key; only `setup_id` and `archived_at` are nullable; no column carries
  a `server_default`; the three FKs target `users.id`, `characters.id`, `setups.id` with no
  `ON DELETE`; exactly one index, non-unique, columns `("user_id", "character_id")` in that
  order; none of `title`, `partner_label`, `rp_language`, `preferred_language`, `model_ref`,
  `system_prompt`, `tools`, `status`, `state` is declared (D8, D4, R2, R4 deferral).
- `backend/app/errors.py` — verified, unchanged. `SessionNotFoundError`
  (`session_not_found`, 404) and `SetupArchivedError` (`setup_archived`, 409) are
  `DomainError` subclasses in `CharacterNotFoundError`'s exact shape, declared after
  `SetupNotFoundError` and before `domain_error_handler`, each raised with no arguments
  giving an empty `detail` (D12).
- `backend/app/models/sessions.py` — verified, unchanged. `SessionResponse` serialises
  exactly the Wire contract's eight keys with no `user_id`, `id` / `character_id` as
  `SnowflakeOut` and `setup_id` its nullable form (decimal strings; `None` → JSON `null`);
  `SessionListResponse` wraps them under the single `sessions` key in the given order;
  `StartSessionRequest` carries `extra="ignore"` and its `OptionalSnowflakeIn` `setup_id`
  resolves absent and `null` to `None`, a decimal string to the `int`, and a non-numeric
  value (string, object, array) to a validation error (D2, R2). The module imports only
  `typing`, `pydantic` and `app.models.ids` — no `fastapi`, no `app.services.`, no `app.db.`.

Behaviour re-checked by running the declarations directly (not the tests); gates from
`backend/`: `mypy app` → "Success: no issues found in 48 source files", `ruff check .` →
"All checks passed!".

### Step 002 — the sessions service

- `backend/app/services/sessions.py` — all fifteen frozen bodies filled (the six operations
  and the nine private helpers); no frozen signature changed. The imports the skeleton
  deferred were added exactly as `002.context.md` lists them (`datetime`'s `UTC` / `datetime`,
  `select`, the three Tables, the four error classes).

Decisions worth knowing:

- **The label join** is built as `sessions.outerjoin(setups, (setups.c.id == sessions.c.setup_id)
  & (setups.c.user_id == user_id))` fed to `select(...).select_from(...)`, so the owner lives in
  the **join condition** and no `setups.archived_at` predicate exists anywhere (D10). The `&`
  form was chosen over importing `and_` to keep the import list to the one the freeze named.
- **Check order inside `with connection.begin():`** is parent → setup existence → setup archive
  state, all *before* `generator.next_id()`, so a refusal inserts nothing and mints no id (D12).
  `_require_choosable_setup` returns the setup's `name`, and the create builds its `RpSession`
  from the inserted values plus that name — no re-read after the insert.
- **`warn_return_any`**: `_require_choosable_setup` assigns the untyped `Row` attribute to a
  declared local (`name: str = row.name`) before returning it, so no `Any` leaks through the
  `str` return. No `# type: ignore` anywhere.
- Archive and restore locate with the joined select inside the `begin()`, write only
  `archived_at` + `updated_at` through `_owned_update` (whose own `WHERE` carries `id` **and**
  `user_id`), re-read with the same joined select after a write, and write nothing at all on a
  no-op — so `last_used_at` is never in any `values()` call in the module (D3, D13).
- All three reads run inside `_reading(...)`, with `list_character_sessions`'s parent check
  **inside** the same guard, so no transaction is left open on the normal return or the raise.

Gates from `backend/`: `.venv/Scripts/python -m mypy app` → "Success: no issues found in 48
source files"; `.venv/Scripts/python -m ruff check .` → "All checks passed!". Behaviour
re-checked by driving the module directly against an in-memory SQLite built from
`metadata.create_all` (not the tests): both lists' order and owner scope, the four refusals
with row counts unchanged, idempotent archive/restore, an archived setup still labelling its
sessions, and `connection.begin()` succeeding after every read and every raise. Longest line
115 chars; the module contains no `delete(`, no uppercase SQL removal keyword, no `fastapi`
import, no `app.services.` import and no model-reference name.

### Step 003 — the sessions router

- `backend/app/routers/sessions.py` — the seven frozen bodies filled (`_to_response` plus the
  six handlers); no frozen signature, decorator, path or status code changed, and no handler
  renamed. The import the skeleton deferred was added exactly as the freeze lists it: the six
  service operations `archive_session, get_session, list_character_sessions, list_sessions,
  restore_session, start_session` joined to the existing `RpSession` in one parenthesised
  `from app.services.sessions import (...)` block (ruff `I` order).
- `backend/app/main.py` — **no change needed**: the import, `include_router(sessions_router)`
  immediately after `include_router(setups_router)` and the two docstring updates were the
  skeleton's real final edit. Verified rather than rewritten — the diff against `master` holds
  exactly those three code-level lines plus the module and `create_app()` docstring wording,
  and the registration order is `…characters_router, setups_router, sessions_router`.

Decisions worth knowing:

- `_to_response` is `SetupResponse`'s counterpart verbatim: one
  `SessionResponse.model_validate(session, from_attributes=True)` (harvest E16's uniform
  conversion). Timestamps are handed through as the stored text — the module contains no
  `datetime` import, no parsing and no formatting — and `user_id` is not a field of either the
  dataclass or the model, so it cannot reach the wire.
- The two list handlers each call their service operation with `current_user.id` as `user_id`
  and wrap the result as `SessionListResponse(sessions=[_to_response(s) for s in owned])`,
  preserving the service's `last_used_at DESC, id DESC` order (D14). The other four answer
  `_to_response(...)` of the single returned `RpSession`.
- The start handler resolves the optional body in one line, `setup_id = None if body is None
  else body.setup_id`, so "no body", `{}` and `{"setup_id": null}` are one identical service
  call with `setup_id=None` (D2, R2). No sentinel and no default setup is substituted.
- **The router catches nothing**: there is no `try`, no `except` and no `HTTPException` in the
  module; the four domain errors propagate to `app.main`'s one `DomainError` handler. It also
  holds no SQL, no `app.db.schema` import and no `app.db` import but `get_connection`.

Gates from `backend/`: `.venv/Scripts/python -m mypy app` → "Success: no issues found in 48
source files"; `.venv/Scripts/python -m ruff check .` → "All checks passed!". Behaviour
re-checked (not the tests) with a throwaway `TestClient` over a temp-file SQLite built from
`metadata.create_all`, with `require_user` / `get_connection` / `get_id_generator` overridden
and raw-inserted users, characters and setups, then deleted: the three no-setup start shapes
and a `{"setup_id": "<S>"}` start answer 201 with `last_used_at == created_at` and
`setup_name` joined; a body carrying `user_id` / `character_id` / `title` is ignored;
`setup_not_found` (404), `setup_archived` (409), `character_not_found` (404) and
`session_not_found` (404) each render with an empty `detail`; both lists come back newest
first and the archived row only under `include_archived=true` while `GET /api/sessions/<id>`
still answers it; archive twice returns the same `archived_at` with `last_used_at` untouched;
`PATCH /api/sessions/<id>` and `DELETE` on all three sessions paths answer 405 with no handler
declared; `/api/sessions/abc`, `/api/characters/abc/sessions` and `{"setup_id": "abc"}` answer
422; and a response body holds exactly the eight wire keys with no `user_id`.

### Step 004 — the sessions API client and the workspace sessions state

- `frontend/src/app/sessionsApi.ts` — the predicate and the six call bodies filled; the private
  `notImplemented` helper removed and `import { apiGet, apiPost } from "../shared/api";` added,
  exactly as the freeze lists. Private path helpers: the `SESSIONS_PATH` constant,
  `characterSessionsPath(characterId)`, `sessionPath(sessionId, suffix = "")` and one
  `withIncludeArchived(listing, includeArchived)` — each id only `encodeURIComponent`-ed, never
  parsed, and no `URLSearchParams` (the query string is just part of the path). No exported
  signature changed.
- `frontend/src/app/sessionsState.ts` — the four free-function bodies filled; `notImplemented`
  removed, `runInAction` joined to the `mobx` import, the value import
  `{ fetchSessions, isSessionArchived }` added beside the existing `import type { Session }`, and
  the module-private `isAbortRejection` added. `SessionsState`'s fields and constructor are
  untouched.

Decisions worth knowing:

- Both listing calls unwrap with `body?.sessions ?? []` over
  `apiGet<SessionListResponse | undefined>` — `setupsApi.ts`'s `fetchSetups` verbatim — so an
  empty 2xx body resolves to an empty array rather than throwing. `fetchSession`,
  `startSession`, `archiveSession` and `restoreSession` return the client's promise directly, so
  every `ApiError` is rethrown unchanged with no branch on `.code` in this layer.
- `startSession` always posts `{ setup_id: setupId }`, so "no setup" is `{"setup_id": null}` on
  the wire; `archiveSession` / `restoreSession` pass `undefined` as the body, so no
  `Content-Type` and no body are sent.
- `loadSessions` mirrors `charactersState.ts`'s `loadCharacters` posture exactly: `signal?.aborted`
  checked first, `runInAction` to `"loading"`, `fetchSessions(false, signal)` (the workspace list
  is working-only, D5 — the flag is never set from here), on a throw a silent return when
  `signal?.aborted || isAbortRejection(error)` else `"failed"` with `sessions` left as they were,
  and a second abort check before writing the rows in the order received plus `"ready"`. It
  never rejects.
- `applySession` filters the id out first and then, for a working row, splices before the first
  remaining row whose `last_used_at` is **strictly less** than the new one's (else pushes) — so
  equal values land after the equal rows and nothing compares or tie-breaks on an id. An
  archived row stops after the filter: removed if present, never inserted (D15). The whole
  upsert runs inside one `runInAction`, and `state.sessions` is reassigned as a fresh array
  rather than mutated in place.
- `orderCharactersByUse` builds one `Map` of the text-max `last_used_at` per character id, then
  decorates each character with its given position and sorts with that position as the
  tie-breaker in every equal case (equal timestamps, and both characters having no session), so
  the order is stable regardless of the engine's sort. A character with no session sorts after
  every character with one. Both `readonly` inputs are only read — the `map` makes the array the
  sort touches.

Gate from `frontend/`: `npm run typecheck` → clean, no output. `npm test` deliberately not run
(verifier-only). A scan of both files found no `id: number`-shaped binding in code or comment,
no `parseInt` / `Number(`, no notification import, and no import outside `../shared/api`, `mobx`
and `./sessionsApi`.

### Step 005 — the start-time label formatter and the collapsed-characters record

- `frontend/src/app/sessionLabel.ts` — `formatSessionStart`'s body filled and the private
  `notImplemented` helper removed; the module still imports nothing at all. It parses with
  `new Date(createdAt)` (the fixed-width form's explicit `+00:00` is valid ISO-8601, and the
  microseconds past milliseconds are truncated, which cannot move a minute boundary — so
  `…23:59:59.999999` stays `23:59`), then formats through
  `Intl.DateTimeFormat(undefined, { timeZone, year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(...)`.
- `frontend/src/app/treeCollapse.ts` — the three bodies filled (`readCollapsedCharacters`,
  `writeCollapsedCharacters`, `toggleCollapsedCharacter`) and `notImplemented` removed;
  `TREE_COLLAPSED_KEY`'s frozen value is untouched and the single **type-only**
  `import type { LayoutStorage } from "./workspaceLayout";` is still the module's only import —
  no value is pulled from `workspaceLayout.ts`, so this module cannot reach 008's key. No
  exported signature changed in either file.

Decisions worth knowing:

- **`formatToParts` assembled by hand, and `hourCycle: "h23"`.** The label is built as
  `` `${year}-${month}-${day} ${hour}:${minute}` `` from a small local `field(type)` lookup over
  the parts, so no locale's own separators, ordering or literal text can reach the output (the
  `en-CA`-style shortcut shifts between ICU versions). `hourCycle: "h23"` is used rather than
  `hour12: false`, which renders midnight as `24` on some engines; checked directly, midnight
  comes out `00:00`. `timeZone: undefined` when the argument is omitted is what makes `Intl`
  use the runtime's own resolved zone, so the no-argument result equals the result for
  `Intl.DateTimeFormat().resolvedOptions().timeZone` by construction rather than by a branch.
- **The read is a chain of early returns**, `workspaceLayout.ts`'s `readStored` posture with its
  own fallback: `null` storage, a throwing `getItem`, an absent key, a `JSON.parse` throw and a
  parsed value that fails `Array.isArray` each return a fresh `[]`. The surviving array is
  filtered in one pass that keeps an entry only when `typeof entry === "string"` and it is not
  already collected — dropping non-strings and duplicates while preserving first-seen order.
  Nothing converts a non-string entry, nothing parses an id as a number, and nothing prunes ids
  for archived or missing characters.
- **The write replaces the whole set**: one `storage.setItem(TREE_COLLAPSED_KEY,
  JSON.stringify(ids))` inside a `try` whose `catch` is empty, with no read-merge step (the
  record *is* the set, unlike 008's two-field patch) and no second key written anywhere in the
  module. A `null` storage returns before the `try`.
- **`toggleCollapsedCharacter` never mutates**: `ids.includes(characterId)` picks between
  `ids.filter(...)` and `[...ids, characterId]`, both fresh mutable `string[]`, appending at the
  end when absent.

Gate from `frontend/`: `npm run typecheck` → clean, no output. `npm test` deliberately not run
(verifier-only). The formatter's zone cases were re-checked by running the same logic through a
throwaway `node -e` snippet (since deleted, no file added): `UTC` / `Asia/Tokyo` /
`America/New_York` for one instant, the zero-padded and 23:59:59.999999 cases, midnight, and
the no-zone form against the resolved zone. A scan of both files found no `window`, no
`document`, no storage global, no `react` / `mobx` / notification import, no `parseInt` and no
`id: number`-shaped text, comments included.

### Step 006 — the tree's session level, chevron and character order

- `frontend/src/app/CharacterTree.tsx` — the whole session level filled behind the frozen
  `CharacterTreeProps`. The three new chevron bodies landed (`TreeChevronExpanded`,
  `TreeChevronCollapsed`, `treeChevronIcon`) and the private `notImplemented` helper was
  removed; `props.sessions` / `props.storage` are now destructured, the `SKELETON (011 step
  006)` docblock paragraph was replaced by what the level actually does, and the imports the
  freeze listed were added exactly (`useState`; `IconChevronDown`; `loadSessions`,
  `orderCharactersByUse`, `sessionsOfCharacter`; `formatSessionStart`; the three
  `./treeCollapse` functions). No frozen signature changed and no 009 render path was altered
  — the header, the three character-level branches, the row links, the active character mark
  and the archived dimming are untouched.
- `frontend/src/app/WorkspaceShell.tsx` — **no change needed**: the `sessions` prop on
  `WorkspaceShellProps`, its destructuring and
  `<CharacterTree characters={characters} sessions={sessions} storage={storage} />` were the
  skeleton's real final edit. Verified against the step file rather than rewritten; the rail,
  the "Collapse tree" row, `UserMenu`, both `closeOverlay` effects and the `main` column are
  as 008 left them.
- `frontend/src/app/App.tsx` — **no change needed**: `const [sessions] = useState(() => new
  SessionsState());` beside the `CharactersState` one, the `SessionsState` value import and
  `sessions={sessions}` on `WorkspaceShell` were likewise already in final form. Verified, not
  rewritten. (The file also already carries steps `008` / `009`'s skeleton — `SessionRoute` at
  `/sessions/:id` and the `sessions` prop on `CharacterScreen` / `CharacterRoute` — which this
  step neither needs nor touches.)

Decisions worth knowing:

- **Two effects, never one.** The sessions load is its own `useEffect` with `[sessions]` as its
  only dependency and its own `AbortController` + `sessionsControllerRef`, mirroring 009's
  characters effect line for line (cleanup aborts and clears the ref when it is still the
  current one). `showArchived` is deliberately absent from its dependency list, so flipping the
  switch re-runs the characters effect alone. "Retry" calls
  `loadSessions(sessions, sessionsControllerRef.current?.signal)`, exactly as the character
  retry does, so an unmount mid-retry aborts it too.
- **The rotated glyph is one chevron, not two icons.** Both wrappers render the same
  `IconChevronDown` with `size` / `stroke` forwarded; the collapsed one adds
  `style={{ transform: "rotate(-90deg)" }}` from a single module constant. Neither takes a
  `collapsed` prop and nothing sets `aria-expanded` — `treeChevronIcon(collapsed)` picks
  between two **module-level** components, so the icon identity is stable and the label change
  ("Collapse <name>" ↔ "Expand <name>") is what carries the state. `IconButton` was not
  widened: `sizeVariant="chevron"` already existed.
- **The chevron is absent, not disabled**, gated on `own.length > 0` where `own` is
  `sessionsOfCharacter(sessions.sessions, character.id)`; the nested list is gated on the same
  flag plus `!rowCollapsed`, so a collapsed character renders the chevron and no list at all.
- **The session row is a Mantine `NavLink component={Link}`**, like the character row:
  `to` is the template `/sessions/<session.id>` with the id interpolated verbatim (no encoding, no
  parsing), `label={formatSessionStart(session.created_at)}` called **without** a zone, and
  the setup label passed as `description={session.setup_name ?? undefined}` — Mantine's own
  dimmed small secondary text, deliberately **not** a `Badge` (badges on this tree mean state).
  With `setup_id` null the description is `undefined`, so the row's only text is the
  start-time label. `aria-current="page"` comes from `session.id === currentSessionId`, where
  `currentSessionId` is `useMatch("/sessions/:id")?.params.id ?? null` — so at a `/sessions/…`
  location no character row is active either (`useMatch("/characters/:id")` does not match).
- **Order and the failed branch.** The ready branch maps
  `orderCharactersByUse(characters.characters, sessions.sessions)`, so while the sessions are
  loading or failed the array is whatever it last held and the order falls back to 009's. When
  `sessions.status === "failed"` the tree renders `Could not load sessions` plus a `Retry`
  button between the header and the character level, and `own` is forced to `[]` so the failed
  state shows the character level with no session rows and no chevrons, exactly as the step
  file words it. `sessions.status` is read in the component body so the `observer` re-renders
  when the load settles, and there is **no** sessions loader anywhere.
- The nested `ul` is a `Box component="ul"` whose `aria-label` is the template
  `Sessions of <character.name>` (role `list` with that name), placed **after** the link
  inside the same character `li`, with `pl="md"` for the indent and the same
  `listStyle: "none"` reset as the "Characters" list.

Gates from `frontend/`: `npm run typecheck` → clean, no output (including both test configs —
nothing under `tests/` errors any more); `npm run build` → built, with only the pre-existing
chunk-size advisory. `npm test` deliberately not run (verifier-only). A scan of the three files
found no notification import, no `parseInt`, no `id: number`-shaped text (comments included)
and no import outside `react`, `mobx-react-lite`, `react-router-dom`, `@mantine/*`,
`@tabler/icons-react` and relative `./` / `../shared/` siblings — no new npm dependency.

### Step 007 — the Sessions section's state

- `frontend/src/app/sessionsSectionState.ts` — all eight frozen free-function bodies filled
  (`loadSectionSessions`, `setShowArchived`, `loadSetupChoices`, `selectSetup`,
  `applySectionSession`, `startSessionFromSection`, `archiveSectionRow`, `restoreSectionRow`);
  the private `notImplemented` helper removed. The imports the freeze deferred were added
  exactly as listed: `runInAction` joined to the `mobx` import, the value import
  `{ archiveSession, fetchCharacterSessions, isSessionArchived, restoreSession, startSession }`
  beside the existing `import type { Session }`, `{ applySession }` beside
  `import type { SessionsState }`, and `{ fetchSetups }` beside `import type { Setup }`. The
  three sentences landed as the module-private, **unexported** `START_FAILED`,
  `ARCHIVE_FAILED`, `RESTORE_FAILED` with the frozen values. No exported signature changed and
  `SessionsSectionState`'s fields and constructor are untouched.

Decisions worth knowing:

- **One shared `runRowAction`, as 010 does** — `archiveSectionRow` / `restoreSectionRow` are
  one line each, passing `archiveSession` / `restoreSession` and their sentence into a private
  `runRowAction(state, workspace, sessionId, action, failureMessage, signal?)`. It takes the
  workspace state as its **second positional parameter**, mirroring the two exported effects,
  so the one body applies the returned row to **both** lists (`applySectionSession` then
  `applySession`) inside a single `runInAction` that also clears `pendingId`.
- **The upsert is remove-then-insert, not 010's replace-in-place.** `applySectionSession`
  filters the id out first, stops there when the row is archived and `showArchived` is false
  (removed if present, never inserted), and otherwise splices before the first remaining row
  whose `last_used_at` is **strictly less** than the new one's (else pushes) — 004's rule
  verbatim, so equal values land after the equal rows, an unchanged `last_used_at` keeps the
  index, and nothing compares or tie-breaks on an id. Visibility goes through a private
  `isVisible(session, showArchived)` over `isSessionArchived`, so no `archived_at` test is
  spelled out twice.
- **Two independent loads, same posture.** `loadSectionSessions` and `loadSetupChoices` each
  follow `charactersState.ts`'s abort-check-first shape (check `signal?.aborted`, `runInAction`
  to `"loading"`, silent return on `signal?.aborted || isAbortRejection(error)` else `"failed"`
  keeping the previous rows, a second abort check before writing) and neither touches the
  other's fields — a failed setup list can never block a start. `loadSetupChoices` calls
  `fetchSetups(characterId, false, signal)`; the flag is never true from here.
- **The selection reset is in the success action only.** The `"ready"` write sets `setups`,
  `setupsStatus` and, in the same `runInAction`, `selectedSetupId = null` when the selection is
  no longer among the returned setups. The failure path writes `setupsStatus` alone, so a
  failed reload keeps both the previous choices and the selection (the server still answers a
  stale choice with 409 `setup_archived`, which lands in `startError`).
- **`startSessionFromSection` reads `selectedSetupId` once, before the request**, and passes it
  straight to `startSession` — `null` for "No setup", no sentinel substituted. Success applies
  the row to both lists and sets `startStatus` `"idle"` in one action, and `onStarted(session.id)`
  is called **after** that action with the id exactly as received (009's `submitCreate` /
  `onCreated` split); the module imports no router. There is deliberately no re-entrancy guard:
  the step specifies none.
- Nothing is written to either list before the server's response arrives on any of the three
  mutating paths, and no path refetches after a mutation (never optimistic, D15).

Gate from `frontend/`: `npm run typecheck` → clean, no output (both tsconfig passes). `npm test`
deliberately not run (verifier-only). Behaviour re-checked (not the tests) by bundling the
module with a throwaway driver outside the repo — a stubbed `fetch` recording method, exact path
and body — and running it under node: 35 checks covering the defaults, both loads' exact paths
(`?include_archived=true` only when the flag is on), order preserved, failure keeping rows,
aborted writes suppressed, the selection kept / reset / kept-on-failure cases, the two start
bodies (`{"setup_id": null}` and `{"setup_id": "s1"}`), never-optimistic while submitting, both
lists plus `onStarted` on success, the three failure sentences with both lists unchanged and
`startStatus` / `pendingId` reset, all four `applySectionSession` branches, archive/restore
against both switch positions, the error cleared before a later action, and `autorun` re-running
after `applySectionSession` and `selectSetup`. A scan of the file found no `id: number`-shaped
text (comments included), no `parseInt` / `Number(`, no notification import, no router import,
nothing imported from `setupsSectionState.ts` and no `URLSearchParams`.

### Step 008 — the Sessions section and its place on the character screen

- `frontend/src/app/SessionsSection.tsx` — the whole body below the frozen region shell filled;
  no frozen signature touched and both scaffolding statements (`void state;`,
  `void NO_SETUP_VALUE;`) deleted. `SessionsSectionProps`, the `observer` declaration, the
  `useState` creation, `useId`, the `<section aria-labelledby>` + `Title order={3}` "Sessions"
  and `NO_SETUP_VALUE = "none"` are unchanged from the freeze; added the imports the SKELETON
  block listed (`useEffect` / `useRef`; `Link` / `useNavigate`; the nine further Mantine
  components; the four glyphs; `IconButton`; `isSessionArchived` + `import type { Session }`;
  `formatSessionStart`; 007's seven functions).
- `frontend/src/app/CharacterScreen.tsx` — **no change needed.** Verified against the freeze:
  `sessions: SessionsState` required on both `CharacterScreenProps` and `CharacterRouteProps`,
  destructured and passed through, and the `SessionsSection` element (keyed by
  `state.characterId`, with `characterId` and `sessions`) sits as the last child of the
  existing-mode `"ready"` `Stack`, immediately after 010's `SetupsSection`, so no section
  renders in new mode or in the `"loading"` / `"not-found"` / `"failed"` branches.
- `frontend/src/app/App.tsx` — **no change needed.** Verified: `sessions={sessions}` on both the
  `/characters/new` `CharacterScreen` and the `/characters/:id` `CharacterRoute`, from the one
  `useState(() => new SessionsState())` step 006 created; nothing else in the file touched.

Decisions worth knowing:

- **Two independent abort controllers, one per load kind** (one `useRef` each): the listing
  controller is created by the `[state, showArchived]` effect and aborted by its own cleanup
  (so a flipped switch cancels the previous listing and an unmount leaves nothing in flight),
  while the choices controller is replaced by a private `reloadSetupChoices()` that aborts any
  in-flight one first. That function is called by a **mount-only** `[state]` effect and by the
  Select's `onDropdownOpen` and nowhere else (D19) — no second render effect, so an unrelated
  re-render issues no request, and a choices reload can never cancel the listing.
- **`NO_SETUP_VALUE` never leaves the component**: the Select's value is
  `state.selectedSetupId ?? NO_SETUP_VALUE`, and `onChange` maps both that value and Mantine's
  `null` back to `null` before calling `selectSetup`, with `allowDeselect={false}` so the field
  cannot be emptied. The setup options carry the id strings verbatim, "No setup" is first, and
  the rest follow `state.setups`' order (R2 — no sentinel reaches the state, the client or the
  wire).
- **Row text**: the `/sessions/<id>` `Link` (a `Text component={Link}`) carries *only*
  `formatSessionStart(session.created_at)`; the `setup_name` is a separate dimmed `Text` beside
  it, rendered only when non-null, so a session with no setup adds no other text
  (US-088.AC-2). An archived row dims the link and adds the `Badge` reading exactly "Archived",
  and its menu offers "Restore" instead of "Archive". The trigger's label is
  `Actions for <start-time label>` — no id and no setup name — and it is wrapped in
  `<Box component="span" display="inline-block">` inside `Menu.Target` (`IconButton` forwards
  no ref). No confirm anywhere.
- **The start is never blocked by the choices**: "Start session" is `disabled` only while
  `state.startStatus === "submitting"`, so an empty or failed setups load still starts a
  session, and the failed load adds only the dimmed line "Could not load setups to choose
  from." under the Select (US-024.AC-3, R2, D18). `onStarted` navigates with
  `navigate(`/sessions/${sessionId}`)` — a push, never `replace` (D1) — with the id as
  received.
- `startError` and `error` each render in their own inline `Alert color="red"` inside the
  region, and every effect call is `void`ed from its handler. No notification call site and no
  notification import anywhere (D18).

Gates from `frontend/`: `npm run typecheck` → clean, no output (both tsconfig passes, including
every test file); `npm run build` → built, 4 entries, no error. `npm test` deliberately not run
(verifier-only). A scan of all three files found no `id: number`-shaped text (comments
included), no `parseInt` / `Number(`, no `@mantine/notifications` or `notifyFailure` import, and
no `ActionIcon` outside `IconButton`. DoD-17 remains a live run.

### Step 009 — the session's own screen at `/sessions/:id`

- `frontend/src/app/sessionScreenState.ts` — the one unimplemented body filled
  (`loadSessionScreen`); no frozen signature changed. `SessionScreenStatus`,
  `SessionScreenState`'s three fields and its constructor, and the module-private
  `SESSION_NOT_FOUND = "session_not_found"` are byte-unchanged from the freeze; the
  scaffolding (`notImplemented`, `void SESSION_NOT_FOUND;`) is gone. The imports the freeze
  named were added: `runInAction` from `mobx`, `isApiError` from `../shared/apiError`,
  `fetchSession` from `./sessionsApi`, plus the module's own `isAbortRejection`.
- `frontend/src/app/SessionScreen.tsx` — `SessionScreen`'s whole render and its load effect
  filled; `SessionScreenProps`, `SessionRouteProps` and `SessionRoute`'s real body (including
  `params.id ?? ""` and `key={sessionId}`) are untouched, and the `notImplemented` scaffolding
  is gone. The freeze's import list was added verbatim (`useEffect` / `useRef`, `Link`, the ten
  Mantine components, `isSessionArchived`, `formatSessionStart`, `loadSessionScreen`).
- `frontend/src/app/App.tsx` — **no change needed.** The `/sessions/:id` route was already
  exactly `<Route path="/sessions/:id" element={<SessionRoute characters={characters} />} />`
  with the `SessionRoute` import after `CharacterScreen`'s; verified against the freeze and the
  file left byte-untouched. Every other route, both `useState` instances and `AppProps` are as
  step 008 left them.

Decisions worth knowing:

- **`loadSessionScreen` is `loadCharacter`'s shape with one branch fewer** (harvest C7): abort
  check first, `runInAction` to `"loading"` so a Retry shows the loader again, then
  `fetchSession(state.sessionId, signal)`; on a throw it returns silently when
  `signal?.aborted || isAbortRejection(error)` (A2: an abort propagates unwrapped, never as an
  `ApiError`), else writes `"not-found"` when `isApiError(error) && error.code === SESSION_NOT_FOUND`
  and `"failed"` otherwise; on success it re-checks the signal before writing `session` plus
  `"ready"`. **No write call of any kind exists in the module** — one `GET` and nothing else, so
  `last_used_at` is untouched (D3), and the workspace `SessionsState` is neither imported nor
  read (an archived session reached by URL is not in it).
- **Branch order in the render** is `"not-found"` → `"failed"` → loader → ready, where the
  loader branch is `state.status !== "ready" || session === null`. That folds `"idle"` and
  `"loading"` together (both show a centred `Center` + `Loader`) and absorbs the impossible
  ready-without-a-row, so the ready render needs no null test.
- **The character link's text is the only thing the `CharactersState` decides** (D17):
  `characters.characters.find((row) => row.id === session.character_id)` by **string
  equality**, with the module-private fallback text `"Character"` when it is absent. The
  `href` is `/characters/${session.character_id}` either way, built from the session's own
  field, and **no request is ever made for the character** — the screen's only call is the one
  `GET`.
- **The ready centre holds no button and no textbox** (DoD-10): an `Anchor component={Link}`,
  a `Title order={2}` whose text is exactly `formatSessionStart(session.created_at)` (called
  with **no** zone argument, 005), the `setup_name` as dimmed small `Text` only when non-null
  (nothing at all otherwise, US-088.AC-2), a `Badge` reading exactly "Archived" when
  `isSessionArchived(session)`, then the line "No entries yet.". No Archive, Restore or
  "Actions for …" control anywhere (D5), no stream, ruler, composer, zone or wall.
- The `"failed"` branch is the only one with a control: the fixed sentence "Could not load the
  session" plus a "Retry" `Button` re-running `loadSessionScreen(state, controllerRef.current?.signal)`
  (D18). `"not-found"` renders "Session not found" alone — the 404 is terminal. **No
  notification import and no notification call site** in either file.
- The mount effect is `CharacterScreen`'s posture verbatim: one `AbortController` per mount,
  stored in a `useRef` for Retry, aborted in the cleanup and cleared only when it is still the
  current one — so a late response after unmount writes nothing.

Gates from `frontend/`: `npm run typecheck` → clean, no output (both tsconfig passes, every file
under `src/` and every test file). `npm test` deliberately not run (verifier-only). A scan of all
three files found no `id`-colon-`number`-shaped text (comments included), no `parseInt` /
`Number.parseInt`, and no `@mantine/notifications` or `notifyFailure` reference. DoD-13 remains a
live run.

## Skeleton

### Step 001 — frozen interface (2026-10-02)

`backend/app/db/schema.py` — `sessions` Table literal, appended **after** `setups` (now the
last statement in the module), bound to the one `metadata`. Eight columns in this order, all
ids `BigInteger().with_variant(Integer(), "sqlite")`, no `server_default` anywhere:

| # | Column | Type | Nullable | Extra |
|---|---|---|---|---|
| 1 | `id` | BigInteger/Integer-variant | NOT NULL | `primary_key=True, autoincrement=False` |
| 2 | `user_id` | BigInteger/Integer-variant | NOT NULL | `ForeignKey("users.id")`, no `ondelete` |
| 3 | `character_id` | BigInteger/Integer-variant | NOT NULL | `ForeignKey("characters.id")`, no `ondelete` |
| 4 | `setup_id` | BigInteger/Integer-variant | **NULL** | `ForeignKey("setups.id")`, no `ondelete`, no default |
| 5 | `last_used_at` | `Text` | NOT NULL | — |
| 6 | `archived_at` | `Text` | **NULL** | — |
| 7 | `created_at` | `Text` | NOT NULL | — |
| 8 | `updated_at` | `Text` | NOT NULL | — |

Plus exactly one index: `Index("ix_sessions_user_id_character_id", "user_id", "character_id")`
— non-unique, columns in that order. No `title`, `partner_label`, `rp_language`,
`preferred_language`, `model_ref`, `system_prompt`, `tools`, `status` or `state` column.
Registry order is now `users, auth_sessions, llm_servers, models, characters, setups, sessions`.

`backend/app/errors.py` — two new `DomainError` subclasses, declared after `SetupNotFoundError`
and before `domain_error_handler`, in `CharacterNotFoundError`'s exact shape (class attributes
plus a default-message `__init__`):

- `class SessionNotFoundError(DomainError)` — new — `code = "session_not_found"`,
  `http_status = 404`, `__init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None`,
  default message `"That session does not exist."`, `detail` empty (`{}`).
- `class SetupArchivedError(DomainError)` — new — `code = "setup_archived"`,
  `http_status = 409`, same `__init__` signature, default message `"That setup is archived."`,
  `detail` empty (`{}`).

`backend/app/models/sessions.py` — new module. Imports only `typing` and `pydantic` plus
`app.models.ids.SnowflakeOut`; imports no `fastapi`, no `app.services.*`, no `app.db.*`.

- `def _parse_optional_snowflake(value: Any) -> int | None` — module-private `BeforeValidator`
  function.
- `OptionalSnowflakeIn = Annotated[int | None, BeforeValidator(_parse_optional_snowflake)]` —
  new type alias, module-level, **the chosen form for the nullable inbound snowflake** (see
  below).
- `class SessionResponse(BaseModel)` — new — no `model_config`; fields in this order:
  - `id: SnowflakeOut`
  - `character_id: SnowflakeOut`
  - `setup_id: SnowflakeOut | None`
  - `setup_name: str | None`
  - `archived_at: str | None`
  - `last_used_at: str`
  - `created_at: str`
  - `updated_at: str`
- `class SessionListResponse(BaseModel)` — new — no `model_config`; one field
  `sessions: list[SessionResponse]`.
- `class StartSessionRequest(BaseModel)` — new — `model_config = ConfigDict(extra="ignore")`
  (the only model of the three that carries it); one field `setup_id: OptionalSnowflakeIn = None`.

Names are unprefixed: `SessionResponse` / `SessionListResponse` / `StartSessionRequest` collide
with nothing under `backend/app/` (harvest C11). No `Rp` prefix.

**The nullable inbound snowflake — form chosen and verified.** `StartSessionRequest.setup_id`
is **not** `SnowflakeIn | None`. It is `OptionalSnowflakeIn`, i.e.
`Annotated[int | None, BeforeValidator(_parse_optional_snowflake)]`, where the validator
returns `None` for `None` ahead of any conversion, otherwise returns `int(value)`, and
re-raises a `TypeError` from `int()` as a `ValueError`. Rationale: `None` never reaches an
`int()` call, and *any* non-numeric JSON value (object, array) answers 422 instead of escaping
as a 500 — `SnowflakeIn | None` happens to handle `null` correctly under pydantic 2.13's smart
union but still lets `{"setup_id": {}}` and `{"setup_id": []}` raise an uncaught `TypeError`
(both forms were measured). Behaviour verified by running all of DoD-8's cases through
`backend/.venv/Scripts/python` against this exact declaration:
`{}` → `setup_id is None`, `model_fields_set == set()`; `{"setup_id": null}` → `None`;
`{"setup_id": "7250000000000000001"}` → the int `7250000000000000001`; `{"setup_id": "abc"}`
→ `ValidationError` (`value_error`); and `{"setup_id": "7", "character_id": "9", "user_id": "1",
"last_used_at": "x", "title": "t"}` → `setup_id == 7` with no other field on the model.
`SessionResponse` serialisation was verified the same way: ints serialise as decimal strings,
`setup_id` / `setup_name` / `archived_at` `None` serialise as JSON `null`, the object has
exactly the eight wire keys and no `user_id`, `SessionListResponse` dumps as `{"sessions": [...]}`
in the given order, and `model_validate(row, from_attributes=True)` works for the router's
uniform conversion.

Gates after the freeze, from `backend/`: `.venv/Scripts/python -m mypy app` → "Success: no
issues found in 46 source files"; `.venv/Scripts/python -m ruff check .` → "All checks passed!".

- Caller-compile edits (out of Source-files scope): **None.** Nothing in `backend/app/` or
  `frontend/` referenced any of these symbols; the three changes are purely additive and no
  existing signature changed.

### Step 002 — frozen interface (2026-10-02)

`backend/app/services/sessions.py` — **new module**, built on `services/setups.py`'s shape
(harvest D12). Imports in the stub: `from collections.abc import Iterator`,
`from contextlib import contextmanager`, `from dataclasses import dataclass`,
`from sqlalchemy import Connection, Row, Select, Update`, `from app.ids import SnowflakeGenerator`.
No `fastapi`, no `app.services.*` import, no `delete`/`DELETE`, no model-reference name (DoD-16
holds on the stub).

**The frozen value — `RpSession`**, `@dataclass(frozen=True)`, no `user_id`, fields in
`SessionResponse`'s wire order (step `001`):

| # | Field | Type |
|---|---|---|
| 1 | `id` | `int` |
| 2 | `character_id` | `int` |
| 3 | `setup_id` | `int \| None` |
| 4 | `setup_name` | `str \| None` |
| 5 | `archived_at` | `str \| None` |
| 6 | `last_used_at` | `str` |
| 7 | `created_at` | `str` |
| 8 | `updated_at` | `str` |

**The six operations** — new, all in `backend/app/services/sessions.py`, `Connection` first and
`user_id` a required positional after it (after the generator, for the create):

- `def start_session(connection: Connection, generator: SnowflakeGenerator, user_id: int, character_id: int, setup_id: int | None = None) -> RpSession`
- `def list_sessions(connection: Connection, user_id: int, include_archived: bool = False) -> list[RpSession]`
- `def list_character_sessions(connection: Connection, user_id: int, character_id: int, include_archived: bool = False) -> list[RpSession]`
- `def get_session(connection: Connection, user_id: int, session_id: int) -> RpSession`
- `def archive_session(connection: Connection, user_id: int, session_id: int) -> RpSession`
- `def restore_session(connection: Connection, user_id: int, session_id: int) -> RpSession`

There is **no** delete, no update and no touch operation, and no other public name in the module.

**The private helpers** — new, signatures frozen, bodies the coder's:

- `def _session_select(user_id: int) -> Select[tuple[int, int, int | None, str | None, str | None, str, str, str]]`
  — the one joined projection (`id`, `character_id`, `setup_id`, `setups.name`, `archived_at`,
  `last_used_at`, `created_at`, `updated_at`), owner-scoped LEFT OUTER JOIN, no `archived_at`
  predicate on the setup (D10). Takes `user_id` because the join condition carries
  `setups.user_id`. Verified with mypy: `select()` at this arity yields
  `Select[*tuple[Any, ...]]`, so this 8-tuple annotation (including `str | None` for the
  outer-joined `setups.name`) typechecks.
- `def _to_session(row: Row[tuple[int, int, int | None, str | None, str | None, str, str, str]]) -> RpSession`
- `def _owned_update(user_id: int, session_id: int) -> Update`
- `def _require_session(connection: Connection, user_id: int, session_id: int) -> RpSession` — raises `SessionNotFoundError`
- `def _fetch_existing(connection: Connection, user_id: int, session_id: int) -> RpSession` — `.one()` inside a known-good transaction
- `def _require_parent_character(connection: Connection, user_id: int, character_id: int) -> None` — own scoped select, raises `CharacterNotFoundError`
- `def _require_choosable_setup(connection: Connection, user_id: int, character_id: int, setup_id: int) -> str` — own scoped select; **returns the setup's current `name`** (which is what the create puts in `setup_name`); raises `SetupNotFoundError` for no row on (`id`, `user_id`, `character_id`) and `SetupArchivedError` for the caller's archived one (D12's check order)
- `@contextmanager def _reading(connection: Connection) -> Iterator[None]` — the read-rollback guard, `@contextmanager` already applied in the stub
- `def _now_text() -> str`

**Imports the coder adds with the bodies** (deliberately absent from the stub — `ruff check .`
fails F401 on an import no stub body uses): `from datetime import UTC, datetime`,
`select` from `sqlalchemy`, `sessions, characters, setups` from `app.db.schema`, and
`CharacterNotFoundError, SessionNotFoundError, SetupArchivedError, SetupNotFoundError` from
`app.errors` — i.e. exactly `002.context.md`'s "Imports" list. Adding them is not a signature
change.

Gates after the freeze, from `backend/`: `.venv/Scripts/python -m mypy app` → "Success: no
issues found in 47 source files"; `.venv/Scripts/python -m ruff check .` → "All checks passed!".

- Caller-compile edits (out of Source-files scope): **None.** Nothing imports
  `app.services.sessions` yet — the router is step `003` — so the new module is purely additive.

### Step 003 — frozen interface (2026-10-02)

`backend/app/routers/sessions.py` — **new module**, built on `routers/setups.py`'s shape
(harvest E16): `router = APIRouter(tags=["sessions"], dependencies=[Depends(require_user)])`
with **no `prefix=`**, each handler carrying its own full path. No SQL, no `app.db.schema`
import, no `try`/`except` anywhere: `SessionNotFoundError`, `CharacterNotFoundError`,
`SetupNotFoundError` and `SetupArchivedError` propagate to the `DomainError` handler
`app.main` already registers. **No `PATCH` handler and no `DELETE` handler.**

Imports in the stub: `from typing import Annotated`; `from fastapi import APIRouter, Depends`;
`from sqlalchemy import Connection`; `from app.db.engine import get_connection`;
`from app.dependencies import CurrentUser, require_user`; `from app.ids import SnowflakeGenerator`;
`from app.models.ids import SnowflakeIn`;
`from app.models.sessions import SessionListResponse, SessionResponse, StartSessionRequest`;
`from app.routers.bootstrap import get_id_generator`; `from app.services.sessions import RpSession`.

**The private conversion** — new:

- `def _to_response(session: RpSession) -> SessionResponse` — the repo's uniform
  `SessionResponse.model_validate(session, from_attributes=True)` conversion; body the coder's.

**The six route handlers** — all new, in declaration order, each decorator and signature
frozen verbatim:

1. `@router.get("/api/sessions", status_code=200)`
   `def list_own_sessions(current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)], include_archived: bool = False) -> SessionListResponse`
2. `@router.get("/api/characters/{character_id}/sessions", status_code=200)`
   `def list_own_character_sessions(character_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)], include_archived: bool = False) -> SessionListResponse`
3. `@router.post("/api/characters/{character_id}/sessions", status_code=201)`
   `def start_own_session(character_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)], generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)], body: StartSessionRequest | None = None) -> SessionResponse`
4. `@router.get("/api/sessions/{session_id}", status_code=200)`
   `def read_own_session(session_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> SessionResponse`
5. `@router.post("/api/sessions/{session_id}/archive", status_code=200)`
   `def archive_own_session(session_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> SessionResponse`
6. `@router.post("/api/sessions/{session_id}/restore", status_code=200)`
   `def restore_own_session(session_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> SessionResponse`

Handler names are `*_own_*` as in 009 / 010. `list_own_character_sessions` is deliberately
**not** `list_character_sessions`: that name belongs to the service function the coder imports.

**The optional body — form chosen and verified.** The body parameter is
`body: StartSessionRequest | None = None` — a plain optional model parameter, **not**
`Body(default=None)`: the pinned FastAPI asserts that a `Body` default may not be set inside
`Annotated`, and a non-`Annotated` `Body(default=None)` would be a defaulted parameter anyway.
Because it carries a default it is declared **last**, after `generator`, exactly as
`include_archived` is declared last on the two list routes (harvest E19); Python forbids a
defaulted parameter before the non-defaulted `Annotated[..., Depends(...)]` ones. A `None`
body and a body whose `setup_id` is absent or `null` are the same request to the service:
`setup_id=None`.

Verified by standing the stub router up in a throwaway `TestClient` through
`backend/.venv/Scripts/python` (`require_user`, `get_connection` and `get_id_generator`
overridden, so the probe observes routing and not the 401), with a second app repeating this
exact signature and reporting the parsed body. All four shapes, on
`POST /api/characters/7250000000000000001/sessions`:

| Request | Stub router | Parsed body (identical signature) |
|---|---|---|
| no body at all | reaches the handler (`NotImplementedError`) | 201, `body is None` |
| `{}` | reaches the handler | 201, `body.setup_id is None` |
| `{"setup_id": null}` | reaches the handler | 201, `body.setup_id is None` |
| `{"setup_id": "99"}` | reaches the handler | 201, `body.setup_id == 99` |
| `{"setup_id": "abc"}` | **422 before the handler** (`value_error` at `["body","setup_id"]`) | 422, same |

The same probe confirmed, on the stub router, 405 for `PATCH /api/sessions/{id}`,
`DELETE /api/sessions/{id}`, `DELETE /api/sessions` and
`DELETE /api/characters/{id}/sessions` with no handler declared, and 422 for
`GET /api/sessions/abc` and `GET /api/characters/abc/sessions`. The probe file was deleted;
no test file was added.

`backend/app/main.py` — **the real, final edit** (not a stub), three changes plus the two
docstrings:

- `from app.routers.sessions import router as sessions_router` — added between the
  `characters`/`health` imports and `from app.routers.setups import router as setups_router`
  (ruff `I` order: `sessions` sorts before `setups`).
- `app.include_router(sessions_router)` — added **immediately after**
  `app.include_router(setups_router)` and before `return app`, so 009's and 010's routes keep
  matching first (D9).
- Module docstring item 5 and the `create_app()` docstring both name the sessions router last,
  as 010 did for 009. No other line of `main.py` changed; the frozen-collaborator import
  comment, the lifespan and the factory order are untouched.

Registration confirmed through `create_app().openapi()`: the nine routers include in order, and
the path table holds `/api/characters…`, `/api/characters/{character_id}/setups`,
`/api/setups/{setup_id}…` unchanged, plus `/api/sessions` (`get`),
`/api/characters/{character_id}/sessions` (`get`, `post`), `/api/sessions/{session_id}` (`get`),
`/api/sessions/{session_id}/archive` (`post`), `/api/sessions/{session_id}/restore` (`post`) —
and **no** `patch` or `delete` operation on any sessions path.

**Imports the coder adds with the bodies** (deliberately absent from the stub — `ruff check .`
fails F401 on an import no stub body uses): the six service operations from
`app.services.sessions`, i.e. `archive_session, get_session, list_character_sessions,
list_sessions, restore_session, start_session` (`RpSession` is already imported, for
`_to_response`'s annotation). Adding them is **not** a signature change.

Gates after the freeze, from `backend/`: `.venv/Scripts/python -m mypy app` → "Success: no
issues found in 48 source files"; `.venv/Scripts/python -m ruff check .` → "All checks passed!".

- Caller-compile edits (out of Source-files scope): **None.** `main.py` is itself a Source file
  of this step, and nothing else references `app.routers.sessions`.

### Step 004 — frozen interface (2026-10-02)

Two new frontend modules, both under `frontend/src/app/`, mirroring `setupsApi.ts` /
`charactersApi.ts` (harvest B3/B4) and `charactersState.ts` (harvest C5). Relative imports
only (no path aliases, F25). No notification API import anywhere (E21). Every id binding is
`string` or `string | null`, in code **and** in comments (E21's scan does not strip comments).

`frontend/src/app/sessionsApi.ts` (**new file**). Imports nothing in the skeleton; one pure
predicate plus the six calls. No update and no delete call (R6).

- `export type Session` — **new**. Eight keys, wire order, no renaming layer:
  `{ id: string; character_id: string; setup_id: string | null; setup_name: string | null; archived_at: string | null; last_used_at: string; created_at: string; updated_at: string }`
- `export type SessionListResponse = { sessions: Session[] }` — **new**. Either listing
  route's body; the siblings' `CharacterListResponse` / `SetupListResponse` counterpart, used
  by the coder to unwrap (`body?.sessions ?? []`).
- `export function isSessionArchived(session: Session): boolean` — **new**. Pure;
  `archived_at !== null`.
- `export async function fetchSessions(includeArchived: boolean, signal?: AbortSignal): Promise<Session[]>` — **new**.
  `GET /api/sessions`, `?include_archived=true` appended **only when true** (the query string
  is part of the path, A1).
- `export async function fetchCharacterSessions(characterId: string, includeArchived: boolean, signal?: AbortSignal): Promise<Session[]>` — **new**.
  `GET /api/characters/<characterId>/sessions`, same query-string rule.
- `export async function fetchSession(sessionId: string, signal?: AbortSignal): Promise<Session>` — **new**.
- `export async function startSession(characterId: string, setupId: string | null, signal?: AbortSignal): Promise<Session>` — **new**.
  `POST /api/characters/<characterId>/sessions`, **always** with the body
  `{ setup_id: <the id or null> }` (`004.context.md`). There is deliberately **no** exported
  input type: the two positional arguments are the whole body.
- `export async function archiveSession(sessionId: string, signal?: AbortSignal): Promise<Session>` — **new**.
- `export async function restoreSession(sessionId: string, signal?: AbortSignal): Promise<Session>` — **new**.

`frontend/src/app/sessionsState.ts` (**new file**). Data class with observable fields only —
no methods, no computed getters; every effect and derivation is a free function. Imports only
`makeAutoObservable` from `mobx` and `import type { Session } from "./sessionsApi"`, so the
module (and the whole step) builds with no dependency on 009 or 010.

- `export type SessionsLoadStatus = "idle" | "loading" | "ready" | "failed"` — **new**. The
  literal union is frozen exactly, in this order (`CharactersLoadStatus` / `SetupsLoadStatus`
  naming).
- `export class SessionsState` — **new**. **Real, not a stub** — the fields and the
  constructor are the declaration the tests bind to. Fields in declaration order, with these
  initial values:
  - `sessions: Session[] = []`
  - `status: SessionsLoadStatus = "idle"`

  **No `showArchived` field** (D5: the workspace list is always the working list).
  `constructor()` takes no arguments and its body is exactly
  `makeAutoObservable(this, {}, { autoBind: true });` — `charactersState.ts`'s call verbatim
  (harvest C5), empty overrides, `autoBind: true`.
- `export async function loadSessions(state: SessionsState, signal?: AbortSignal): Promise<void>` — **new**.
- `export function applySession(state: SessionsState, session: Session): void` — **new**. D15's
  remove-then-insert upsert.
- `export function sessionsOfCharacter(sessions: readonly Session[], characterId: string): Session[]` — **new**. Pure.
- `export function orderCharactersByUse<T extends { id: string }>(characters: readonly T[], sessions: readonly Session[]): T[]` — **new**.
  Pure, **generic exactly as written**: constrained to "anything with an `id` string", the
  element type returned unchanged, so step 006 passes 009's `Character` rows through it and
  gets `Character[]` back without this module importing `charactersApi.ts`. The two
  `readonly` array parameters are the `modelPicker.ts` convention and compile-enforce DoD-8's
  "inputs are not mutated"; a plain `Session[]` / `Character[]` (including a MobX observable
  array) is assignable to them, so no call site needs a cast.

Skeleton scaffolding the **coder must remove**, and what it must add in its place (omitted
here because `noUnusedLocals` / `noUnusedParameters` fail an import or a parameter nothing
reads yet — a compile constraint, **not** a contract change):

- Both files declare a private `function notImplemented(name: string, ...args: unknown[]): never`
  and every function body is `return notImplemented("<name>", …every parameter…)`. Nothing
  returns a placeholder value, builds a path, issues a request, orders anything or writes to
  the state. The helper goes away once the bodies land; the exported signatures above do not.
  `SessionsState`'s fields and constructor are **not** scaffolding and stay as they are.
- `sessionsApi.ts` must gain `import { apiGet, apiPost } from "../shared/api";` and the
  private path helpers (the `/api/sessions` constant, a `characterSessionsPath(characterId)`
  and a `sessionPath(sessionId, suffix = "")`, each `encodeURIComponent`-ing the id and never
  parsing it, per `setupsApi.ts:37-46`). Private helpers are **not** frozen — shape them as
  convenient, but no `URLSearchParams` and no id coercion. `archiveSession` / `restoreSession`
  pass `undefined` as the body; `startSession` passes `{ setup_id: setupId }`.
- `sessionsState.ts` must gain `runInAction` from `mobx` (the skeleton imports
  `makeAutoObservable` only), the value import `fetchSessions` from `./sessionsApi` (the
  skeleton imports only `import type { Session }`), and its own
  `isAbortRejection(error) { return error instanceof Error && error.name === "AbortError"; }`
  — `charactersState.ts`'s abort-check-first posture (C5): check `signal?.aborted` first,
  `runInAction` to `"loading"`, on a throw return silently when
  `signal?.aborted || isAbortRejection(error)` else set `"failed"` and keep the previous rows,
  on success re-check the signal before writing rows plus `"ready"`.
  `isSessionArchived` is imported only if the coder's `applySession` uses it (D15's archived
  branch may read `archived_at` directly); that choice is not a signature change.

Gate after the freeze, from `frontend/`: `npm run typecheck`
(`tsc --noEmit -p tsconfig.json && tsc --noEmit -p tsconfig.node.json`) → clean, no output.
`npm test` was deliberately not run (verifier-only). A direct scan of both new files for
`\b\w*(id|Id)\s*\??\s*:\s*number\b`, `parseInt` and any `notifications` import found nothing.

- Caller-compile edits (out of Source-files scope): **None.** Both modules are new and nothing
  imports them yet — `App.tsx`, `CharacterTree.tsx`, `charactersApi.ts`, `setupsApi.ts` and
  every other frontend file are untouched. No signature of an existing symbol changed.

### Step 005 — frozen interface (2026-10-02)

Two new frontend modules, both under `frontend/src/app/`, both **pure and DOM-free**: neither
source references `window`, `document`, a browser storage global, React or MobX, in code or in
comments (DoD-10 is a source scan, and a mention in a comment would count). Relative imports
only (no path aliases, F25). No notification API import (E21). Ids stay strings: no numeric
check, no `parseInt`, and no `id`-colon-`number` shaped text anywhere, comments included
(E21's scan does not strip comments).

`frontend/src/app/sessionLabel.ts` (**new file**). Imports nothing at all. One exported symbol.

- `export function formatSessionStart(createdAt: string, timeZone?: string): string` — **new**.
  Pure. `createdAt` is a session's `created_at` in `data-model.md`'s fixed-width form
  (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`); `timeZone` is an optional IANA zone name. Returns
  `YYYY-MM-DD HH:MM` — 24-hour, zero-padded, a single space — in that zone, or in the
  runtime's own resolved zone when the argument is omitted (`undefined`). The second parameter
  is **optional, not nullable**: `string | undefined` via `?`, never `string | null`, so
  components call `formatSessionStart(session.created_at)` and the formatter tests pass a zone.

`frontend/src/app/treeCollapse.ts` (**new file**). Its only import is the **type-only**
`import type { LayoutStorage } from "./workspaceLayout";` — the type and nothing else. The
module never reads or writes `rphelper.workspace-layout`, and it is a sibling of
`workspaceLayout.ts` / `shellState.ts` (F27), not an extension of either.

- `export const TREE_COLLAPSED_KEY = "rphelper.tree-collapsed";` — **new**. The literal value
  is part of the declaration and is **real, not a stub**: exactly `"rphelper.tree-collapsed"`.
  No type annotation, so its type is the string literal — `WORKSPACE_LAYOUT_KEY`'s form (C8).
- `export function readCollapsedCharacters(storage: LayoutStorage | null): string[]` — **new**.
  Total read, never throws; returns a plain mutable `string[]` (the tree hands it straight to
  `useState`).
- `export function writeCollapsedCharacters(storage: LayoutStorage | null, ids: readonly string[]): void` — **new**.
  Best-effort write, never throws, no-op on `null` storage, writes only `TREE_COLLAPSED_KEY`.
- `export function toggleCollapsedCharacter(ids: readonly string[], characterId: string): string[]` — **new**.
  Pure; a **new** array with `characterId` appended when absent or removed when present.

**Why the two array parameters are `readonly string[]`** (step 004's `orderCharactersByUse` /
`sessionsOfCharacter` precedent, from `modelPicker.ts`): it compile-enforces DoD-9's "the input
arrays are unchanged afterwards" and DoD-7's "writes the array it was given", while a plain
`string[]` literal, a `useState` array and a MobX observable array are all assignable to it, so
no call site and no test needs a cast. The **returns** are mutable `string[]`, so a caller may
pass a returned array back into either function unchanged.

Skeleton scaffolding the **coder must remove**, and what it must add in its place (listed here
because `noUnusedLocals` / `noUnusedParameters` are on and would fail an import or a parameter
no stub body reads — a compile constraint, **not** a contract change, exactly as steps 002–004
recorded):

- Each file declares a private
  `function notImplemented(name: string, ...args: unknown[]): never` (step 004's helper
  verbatim) and every function body is `return notImplemented("<name>", …every parameter…)`.
  Nothing returns a placeholder value, parses a timestamp, formats anything, touches a storage
  or builds an array. The helper goes away with the bodies; the exported signatures above and
  `TREE_COLLAPSED_KEY`'s value do not.
- `sessionLabel.ts`'s body needs **no new import**: `Date` and `Intl` are globals, and
  `005.context.md` fixes the approach (`new Date(createdAt)`, then
  `Intl.DateTimeFormat(undefined, { timeZone, year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(...)` assembled by hand
  — never a locale's own separators or ordering, never `hour12: false`). Passing
  `timeZone: undefined` is what makes `Intl` use the runtime's zone, which is DoD-4's
  comparison. `Intl` is in scope under the pinned `lib` (ES2022 + DOM) with no config change.
- `treeCollapse.ts` keeps its single type-only import; the bodies add only `try` / `catch`
  around `getItem`, `JSON.parse` and `setItem` plus the string/duplicate filtering — no value
  import from `workspaceLayout.ts` (importing one would make this module read 008's key, which
  it must not).

Gate after the freeze, from `frontend/`: `npm run typecheck`
(`tsc --noEmit -p tsconfig.json && tsc --noEmit -p tsconfig.node.json`) → clean, no output.
`npm test` was deliberately not run (verifier-only). A direct scan of both new files for
`window`, `document`, a storage global, a `react` / `mobx` / notifications import, `parseInt`
and `\b\w*(id|Id)\s*\??\s*:\s*number\b` found nothing (DoD-10 pre-checked against the stubs).

- Caller-compile edits (out of Source-files scope): **None.** Both modules are new and nothing
  imports them yet — `workspaceLayout.ts`, `shellState.ts`, `CharacterTree.tsx`,
  `WorkspaceShell.tsx`, `App.tsx` and every other frontend file are untouched, and no signature
  of an existing symbol changed.

### Step 006 — frozen interface (2026-10-02)

Three **existing** frontend components edited; no new file. All three changes are additive
props plus one new glyph wrapper — **no existing signature was removed or renamed**, and every
009 / 008 render path in all three files is untouched. Relative imports only (F25). No
notification import (E21). No `parseInt` and no id-colon-`number`-shaped text anywhere,
comments included (E21's scan does not strip comments). `IconButton` is **not** widened:
`sizeVariant: "chevron"` already exists (harvest D14).

`frontend/src/app/CharacterTree.tsx` — **changed**.

- `export type CharacterTreeProps` — **changed** (was `{ characters: CharactersState }`), now
  in full, in declaration order, both additions **required**:
  - `characters: CharactersState`
  - `sessions: SessionsState`
  - `storage: LayoutStorage | null`

  New type-only imports: `import type { SessionsState } from "./sessionsState";`,
  `import type { LayoutStorage } from "./workspaceLayout";`,
  `import type { IconButtonProps } from "../shared/IconButton";`.
- `export const CharacterTree` — **signature unchanged**
  (`observer(function CharacterTree(props: CharacterTreeProps): React.JSX.Element)`); only its
  props type widened.

The rotated chevron glyph (D7; genuinely new — harvest D14 confirms no rotating-icon precedent
exists, that `IconButton` has no rotation prop and that it forwards no ref). Four new exported
symbols, all declared in `CharacterTree.tsx`:

- `export type TreeChevronProps = { size?: number | string; stroke?: number }` — **new**.
  Exactly the props `IconButton` hands its `icon` component and nothing else: no `collapsed`,
  no `aria-expanded` (the label change carries the state). A required extra prop would make the
  component unassignable to `IconButtonProps["icon"]`, which is why the collapsed state selects
  between two components instead of being passed in.
- `export const TreeChevronExpanded: IconButtonProps["icon"] = (props: TreeChevronProps) => …`
  — **new**. The unrotated glyph. The annotation sits on the **const**, so assignability to
  `IconButton`'s `icon` prop is compile-proved at the declaration, not at the call site.
- `export const TreeChevronCollapsed: IconButtonProps["icon"] = (props: TreeChevronProps) => …`
  — **new**. The **same** `IconChevronDown`, rotated `-90°` by a style on the wrapper
  ("one chevron, rotated, not two icons").
- `export function treeChevronIcon(collapsed: boolean): IconButtonProps["icon"]` — **new**.
  Picks a row's glyph from its collapsed state; returns one of the two module-level components,
  so the identity is stable across renders and the icon never remounts. The coder's chevron is
  `<IconButton icon={treeChevronIcon(collapsed)} label={…} sizeVariant="chevron" onClick={…} />`.

`frontend/src/app/WorkspaceShell.tsx` — **changed**.

- `export type WorkspaceShellProps` — **changed** (one required addition), now in full:
  `{ user: CurrentUser; storage: LayoutStorage | null; characters: CharactersState;
  sessions: SessionsState; children: React.ReactNode }`.
- `export const WorkspaceShell` — signature unchanged. It destructures `sessions` and passes it
  with its existing `storage` to the tree: the expanded branch now mounts
  `<CharacterTree characters={characters} sessions={sessions} storage={storage} />`. Nothing
  else in the file changed — the rail, the "Collapse tree" row, `UserMenu`, the grid element,
  both `closeOverlay` effects and the `main` column are untouched.

`frontend/src/app/App.tsx` — **changed**.

- `export type AppProps` — **unchanged** (`{ user: CurrentUser; storage: LayoutStorage | null }`).
- One new store creation, the exact line, immediately after the `CharactersState` one:
  `const [sessions] = useState(() => new SessionsState());`
  with the value import `import { SessionsState } from "./sessionsState";`. Created **once**
  and passed down as a prop — no context, no module singleton (D15, "No context, no methods").
- `WorkspaceShell` now receives `sessions={sessions}` beside `user`, `storage`, `characters`
  (the element was reflowed onto several lines; no other change).
- **Routes and screens are untouched in this step**: `/sessions/:id` is still `element={null}`
  (step 009's), and `CharacterScreen` / `CharacterRoute` still receive only `characters`
  (step 008's).

**Left unimplemented for the coder — the whole session level.** Nothing of the new rendering is
half-built, so there is no partial markup for the coder to undo:

- the three new function bodies above (`TreeChevronExpanded`, `TreeChevronCollapsed`,
  `treeChevronIcon`) throw through a private
  `function notImplemented(name: string, ...args: unknown[]): never` — step 004's helper
  verbatim. Nothing returns a placeholder glyph or any plausible value, and no existing render
  path calls any of them, so every 009 / 008 assertion still renders.
- inside `CharacterTree`, `props.sessions` and `props.storage` are **deliberately not
  destructured** (an unread local fails `noUnusedLocals`; an unread **prop** is legal). A
  `SKELETON (011 step 006)` block on the component's docblock names each piece as the coder's:
  the separate sessions-load effect (`loadSessions`, its own `AbortController`, **no**
  `showArchived` dependency), the `orderCharactersByUse` row order, the component-local
  collapsed set (`useState` initialised from `readCollapsedCharacters(props.storage)`,
  `toggleCollapsedCharacter`, `writeCollapsedCharacters`), the per-row chevron `IconButton`
  (absent when the character has no session), the nested "Sessions of <name>" list of
  `/sessions/<id>` links from `sessionsOfCharacter` with `formatSessionStart` and the dimmed
  setup label, the `useMatch("/sessions/:id")` active mark, and the inline
  "Could not load sessions" + "Retry" branch.
- **Imports the coder adds with the bodies** (absent here only because `noUnusedLocals` fails an
  import no stub body reads — a compile constraint, **not** a contract change, exactly as steps
  002–005 recorded): `loadSessions`, `sessionsOfCharacter`, `orderCharactersByUse` from
  `./sessionsState`; `formatSessionStart` from `./sessionLabel`; `readCollapsedCharacters`,
  `writeCollapsedCharacters`, `toggleCollapsedCharacter` from `./treeCollapse`;
  `IconChevronDown` from `@tabler/icons-react` (F24: already installed — no new dependency);
  `useState` from `react`. Adding them is not a signature change.

Gate after the freeze, from `frontend/`: `npm run typecheck`
(`tsc --noEmit -p tsconfig.json && tsc --noEmit -p tsconfig.node.json`) — **every file under
`src/` compiles clean**, and the `tsconfig.node.json` pass is clean. Exactly two errors remain,
**both in test files and both the expected missing-required-prop fallout that the test-coder's
DoD-10..13 amendments fix**:

- `tests/app/CharacterTree.test.tsx(186,12)` TS2739 — its render helper passes `{ characters }`
  only, so `sessions` and `storage` are missing from `CharacterTreeProps`;
- `tests/app/WorkspaceShell.test.tsx(186,10)` TS2741 — its `renderShell` helper is missing
  `sessions` from `WorkspaceShellProps`.

`tests/app/App.test.tsx`, `tests/app/AppBoot.test.tsx` and `tests/entries.test.tsx` **typecheck
clean** (they mount `App`, whose props did not change); their amendments are runtime-only — each
`fetch` stub must answer `GET /api/sessions` (harvest E16 / E18), which is the test-coder's work
and is invisible to `tsc`. No test file was touched by this step. `npm test` was deliberately
not run (verifier-only).

- Caller-compile edits (out of Source-files scope): **None.** The only source call sites of
  `CharacterTree` and `WorkspaceShell` are inside this step's own three files
  (`WorkspaceShell.tsx` → `CharacterTree`, `App.tsx` → `WorkspaceShell`); no other file under
  `frontend/src` imports either. `AppBoot.tsx` renders `App`, whose props are unchanged. No file
  outside the Source list was modified.

### Step 007 — frozen interface (2026-10-02)

One **new** frontend module, `frontend/src/app/sessionsSectionState.ts`; nothing else was
created or edited. It copies `setupsSectionState.ts`'s posture (harvest C6) and
`charactersState.ts`'s abort-check-first effect shape (C5). Relative imports only, no path
aliases (F25). **No router import** anywhere in the module (navigation is reported through
`onStarted`, `007.context.md`). **No notification API import** (E21, D18). Nothing is imported
from 010's `setupsSectionState.ts`. Every id binding is `string` or `string | null`, in code
**and** in comments (E21's scan does not strip comments).

Skeleton imports (all four are used by the declarations, so they are already present):
`import { makeAutoObservable } from "mobx";`, `import type { Session } from "./sessionsApi";`,
`import type { SessionsState } from "./sessionsState";`,
`import type { Setup } from "./setupsApi";`.

Two exported status unions — frozen exactly, in this order:

- `export type SessionsSectionLoadStatus = "idle" | "loading" | "ready" | "failed"` — **new**.
  **One** union used by **both** `status` and `setupsStatus` (the two loads are independent but
  their states are the same four).
- `export type SessionStartStatus = "idle" | "submitting"` — **new**. No `"failed"` member: a
  start failure is `startError`.

`export class SessionsSectionState` — **new**. **Real, not a stub** — the fields and the
constructor are the declaration the tests bind to. Observable fields only: no methods, no
computed getters. Fields in declaration order, with these exact initial values:

| Field | Type | Initial value |
|---|---|---|
| `characterId` | `string` | the constructor argument (no default) |
| `sessions` | `Session[]` | `[]` |
| `status` | `SessionsSectionLoadStatus` | `"idle"` |
| `showArchived` | `boolean` (inferred from `= false`) | `false` |
| `setups` | `Setup[]` | `[]` |
| `setupsStatus` | `SessionsSectionLoadStatus` | `"idle"` |
| `selectedSetupId` | `string \| null` | `null` |
| `startStatus` | `SessionStartStatus` | `"idle"` |
| `startError` | `string \| null` | `null` |
| `error` | `string \| null` | `null` |
| `pendingId` | `string \| null` | `null` |

`constructor(characterId: string)` — body exactly `this.characterId = characterId;` then
`makeAutoObservable(this, {}, { autoBind: true });` (`setupsSectionState.ts`'s constructor
verbatim). **No field holds the workspace `SessionsState`** and none is persisted (D5).

The eight exported free functions — exact signatures, in declaration order:

- `export async function loadSectionSessions(state: SessionsSectionState, signal?: AbortSignal): Promise<void>` — **new**.
- `export function setShowArchived(state: SessionsSectionState, showArchived: boolean): void` — **new**.
  (Same name as `setupsSectionState.ts`'s and `charactersState.ts`'s; a different module, so no
  collision — the section component imports it under this name or aliases it locally.)
- `export async function loadSetupChoices(state: SessionsSectionState, signal?: AbortSignal): Promise<void>` — **new**.
- `export function selectSetup(state: SessionsSectionState, setupId: string | null): void` — **new**.
- `export function applySectionSession(state: SessionsSectionState, session: Session): void` — **new**.
- `export async function startSessionFromSection(state: SessionsSectionState, workspace: SessionsState, onStarted: (sessionId: string) => void, signal?: AbortSignal): Promise<void>` — **new**.
  The callback type is frozen inline — one positional `string` argument, `void` return; there is
  deliberately **no** exported callback type alias.
- `export async function archiveSectionRow(state: SessionsSectionState, workspace: SessionsState, sessionId: string, signal?: AbortSignal): Promise<void>` — **new**.
- `export async function restoreSectionRow(state: SessionsSectionState, workspace: SessionsState, sessionId: string, signal?: AbortSignal): Promise<void>` — **new**.

`workspace: SessionsState` is the **second positional parameter** of exactly these three
effects and a parameter nowhere else; the five other functions never see it
(`007.context.md`, "Why the workspace state is a parameter, not a field").

Skeleton scaffolding the **coder must remove**, and what it must add in its place (omitted here
only because `noUnusedLocals` / `noUnusedParameters` fail an import, a constant or a parameter
that no stub body reads — a compile constraint, **not** a contract change, exactly as steps
002–006 recorded):

- The module declares a private `function notImplemented(name: string, ...args: unknown[]): never`
  (step 004's helper verbatim) and every free function's body is
  `return notImplemented("<name>", …every parameter…)`. Nothing returns a placeholder value,
  issues a request, orders anything, calls `onStarted` or writes to either state. The helper
  goes away once the bodies land; the signatures above do not. The class's fields and
  constructor are **not** scaffolding and stay as they are.
- **Value imports the coder adds** (the skeleton has the four type-/`mobx`-only imports above):
  `runInAction` from `"mobx"`; `fetchCharacterSessions`, `startSession`, `archiveSession`,
  `restoreSession` from `"./sessionsApi"` (and `isSessionArchived` only if the coder's
  visibility test uses it rather than reading `archived_at` — that choice is not a signature
  change); `applySession` from `"./sessionsState"`; `fetchSetups` from `"./setupsApi"`
  (`fetchSetups(state.characterId, false, signal)` — `includeArchived` is **always** false
  here: archived setups are never offered, D1 / D19).
- **The three fixed failure sentences the coder adds** as module-private constants, deliberately
  **not exported** (nothing may assert against the constant instead of the spec's literal).
  Frozen names and exact values (D18):
  - `const START_FAILED = "Could not start the session.";`
  - `const ARCHIVE_FAILED = "Could not archive the session.";`
  - `const RESTORE_FAILED = "Could not restore the session.";`
- Other private helpers the coder may shape as convenient — **not frozen, none exported**: an
  `isAbortRejection(error)` (`error instanceof Error && error.name === "AbortError"`), an
  `isVisible(session, showArchived)`, and a shared `runRowAction(…)` body behind
  `archiveSectionRow` / `restoreSectionRow` (harvest C6). No `URLSearchParams`, no id coercion,
  no ordering by id, no `notifyFailure`, no router import, no refetch after a mutation.

Gate after the freeze, from `frontend/`: `npm run typecheck`
(`tsc --noEmit -p tsconfig.json && tsc --noEmit -p tsconfig.node.json`).
`sessionsSectionState.ts` and **every other file under `src/`** compile clean, and the
`tsconfig.node.json` pass is clean (run separately, exit 0, because the `&&` short-circuits).
Exactly the **two pre-existing** errors from step 006's freeze remain, both in test files the
test-coder owns and this step did not touch:

- `tests/app/CharacterTree.test.tsx(186,12)` TS2739 — missing `sessions`, `storage`;
- `tests/app/WorkspaceShell.test.tsx(186,10)` TS2741 — missing `sessions`.

**This step added no new error.** `npm test` was deliberately not run (verifier-only). A direct
scan of the new file for the `ids-are-strings` id-colon-number pattern, `parseInt` and any
`notifications` import found nothing.

- Caller-compile edits (out of Source-files scope): **None.** The module is new and nothing
  imports it yet (`SessionsSection.tsx` is step 008's). No existing signature changed, and no
  file outside the Source list was modified — `sessionsApi.ts`, `sessionsState.ts`,
  `setupsApi.ts`, `setupsSectionState.ts` and every component are untouched.

### Step 008 — frozen interface (2026-10-02)

One **new** frontend component, `frontend/src/app/SessionsSection.tsx`, plus two **existing**
components edited additively: `CharacterScreen.tsx` and `App.tsx`. No existing signature was
removed or renamed, and every 008 / 009 / 010 render path in both edited files is otherwise
untouched. Relative imports only, no path aliases (F25). No notification API import anywhere
(E21: the one textual mention of `shared/notifyFailure` is a comment naming what is *not*
imported; `conventions.test.ts` keys on an `@mantine/notifications` import, of which there is
none). No `parseInt` and no id-colon-`number`-shaped text in any of the three files, comments
included (E21's scan does not strip comments). `IconButton` is **not** widened:
`sizeVariant: "inline"` already exists (harvest D14).

`frontend/src/app/SessionsSection.tsx` (**new file**).

- `export type SessionsSectionProps` — **new**. In full, in declaration order, both props
  **required**:
  - `characterId: string` — the character whose sessions the section lists and starts; a
    string, never parsed.
  - `sessions: SessionsState` — the one workspace sessions state `App` creates (D15), handed
    to 007's start and row-action effects so a mutated row lands in the tree with no refetch.

  The only module imports are `import type { SessionsState } from "./sessionsState";` and
  `import { SessionsSectionState } from "./sessionsSectionState";` (plus React,
  `mobx-react-lite`, and the two Mantine components the shell uses). **No prop for the section
  state** and no callback prop: the section creates its own state and reports nothing upward.
- `export const SessionsSection` — **new**.
  `observer(function SessionsSection(props: SessionsSectionProps): React.JSX.Element)` —
  `SetupsSection`'s declaration form verbatim (010 `006`). It destructures `characterId` only
  and creates its state once with
  `const [state] = useState(() => new SessionsSectionState(characterId));` (never `useMemo`),
  and takes the heading's id from `const headingId = useId();`.
- **The region shell is frozen, not behaviour** — 009's `CharacterScreen.test.tsx` already
  asserts a heading matching `/^sessions$/i` (harvest E19) and step 008 DoD-12 pins the
  region's document order, so it is declared here exactly as `SetupsSection` produces its own
  (harvest D13):

  ```tsx
  <section aria-labelledby={headingId}>
    <Stack gap="xs">
      <Title order={3} id={headingId}>
        Sessions
      </Title>
    </Stack>
  </section>
  ```

  So the region's role is `region`, its accessible name is "Sessions", and its heading sits at
  `Title order={3}` — the same level as 010's "Setups" heading and the level 009's bare
  heading used. `aria-label` is deliberately not used.
- `const NO_SETUP_VALUE = "none";` — **new, module-private, deliberately NOT exported.** The
  "No setup" option's fixed value: Mantine's `Select` speaks strings and treats `null` as
  "nothing selected" (which would let the field be emptied), and this value can never equal a
  decimal snowflake. It lives **only** in this module — the coder maps it to `null` before
  calling `selectSetup` and back to it for the displayed value, so it never reaches the section
  state, the API client or the wire (R2, "no sentinel"; `008.context.md`). The setup options'
  values are the setup id strings verbatim. Nothing may assert against the constant instead of
  the spec's literal, which is why it is not exported.

**Left unimplemented for the coder — the whole body below the heading.** None of it is
half-built, so there is no partial markup to undo, and an absent control cannot accidentally
satisfy a DoD assertion. A `SKELETON (011 step 008)` block at the top of the file names each
piece as the coder's, with its exact accessible name, text and disabled rule from the step
file: the two load effects (`loadSectionSessions` on mount and on every `showArchived` change;
`loadSetupChoices` on mount and again on each `onDropdownOpen`, D19 — each kind with its **own**
`AbortController` in its own ref, aborted when its next run starts and on unmount, every effect
`void`ed from its handler); the "Show archived sessions" `Switch`; the inline start (the "Setup"
`Select` with "No setup" first and `allowDeselect={false}`, the dimmed "Could not load setups to
choose from." under it while `setupsStatus === "failed"`, and the "Start session" `Button` with
`IconPlus`, disabled **only** while `startStatus === "submitting"`, whose `onStarted` pushes
`/sessions/<id>` through `useNavigate` — a push, not a `replace`, D1); the `startError` and
`error` `Alert`s; the four list branches (`Loader` / "Could not load sessions" + "Retry" /
"No sessions yet." / `Table`); and each row (the `/sessions/<id>` `Link` whose text is
`formatSessionStart(session.created_at)` with no zone argument, the `setup_name` or nothing at
all, the dimming plus the "Archived" `Badge`, and the one overflow `Menu` behind the
`IconButton icon={IconDots} sizeVariant="inline"` labelled `Actions for <start-time label>`,
disabled while `pendingId === session.id`, **wrapped in
`<Box component="span" display="inline-block">` inside `Menu.Target`** because `IconButton`
forwards no ref and a bare `ActionIcon` is forbidden — harvest D13 — with the "Archive" /
"Restore" items and no confirm).

Two **scaffolding statements the coder deletes** (`void state;` and `void NO_SETUP_VALUE;`),
present only because `noUnusedLocals` fails a local nothing reads — a compile constraint,
**not** a contract change, exactly as steps 002–007 recorded. `props.sessions` needs no such
line: an unread *prop* is legal where an unread local is not. The **imports the coder adds with
the body** are listed in the file's SKELETON block (`useEffect` / `useRef`; `Link` /
`useNavigate`; the nine further Mantine components; the four `@tabler/icons-react` glyphs — all
already installed, F24, no new dependency; `IconButton`; `isSessionArchived` and
`import type { Session }`; `formatSessionStart`; and 007's seven effect/setter functions).
Adding them is not a signature change.

`frontend/src/app/CharacterScreen.tsx` — **changed**.

- `export type CharacterScreenProps` — **changed** (was
  `{ characters: CharactersState; characterId: string | null }`), now in full, in declaration
  order, the addition **required**:
  `{ characters: CharactersState; characterId: string | null; sessions: SessionsState }`.
  Required in **both** modes even though new mode renders no section: one prop, no optional
  branch. New type-only import `import type { SessionsState } from "./sessionsState";` plus the
  value import `import { SessionsSection } from "./SessionsSection";`.
- `export const CharacterScreen` — **signature unchanged**
  (`observer(function CharacterScreen(props: CharacterScreenProps): React.JSX.Element)`); only
  its props type widened. It now destructures
  `const { characters, characterId, sessions } = props;`.
- **The exact replacement in the existing-mode `"ready"` branch.** 009's two lines

  ```tsx
  {/* Heading only; 011 fills the section with the character's sessions. */}
  <Title order={3}>Sessions</Title>
  ```

  are replaced, in the same position — immediately **after** 010's
  `{state.characterId !== null && (<SetupsSection key={state.characterId} characterId={state.characterId} />)}`
  and as the last child of the `"ready"` `<Stack>` — by

  ```tsx
  {state.characterId !== null && (
    <SessionsSection
      key={state.characterId}
      characterId={state.characterId}
      sessions={sessions}
    />
  )}
  ```

  A **second** `state.characterId !== null` guard rather than one shared guard, so 010's
  element stays byte-untouched. The guard is only strictness (existing mode has already
  returned when the id was null). Mounted **only** here: new mode, `"loading"`, `"not-found"`
  and `"failed"` return earlier and render no section (DoD-12). `Title` stays imported — the
  two `<Title order={2}>` headings still use it. Document order in `"ready"` is therefore: name
  heading → error → Name → Persona → the action `Group` → "Setups" region → "Sessions" region
  (DoD-12), and 010's "Setups precedes the Sessions heading" stays true because the region
  carries its own `Title order={3}` "Sessions" heading. One docblock phrase ("an empty
  'Sessions' section") was corrected to name both sections; no other line of the file changed.
- `export type CharacterRouteProps` — **changed** (was `{ characters: CharactersState }`), now
  in full: `{ characters: CharactersState; sessions: SessionsState }`.
- `export function CharacterRoute(props: CharacterRouteProps): React.JSX.Element` —
  **signature unchanged**; it destructures `sessions` and passes it straight through:
  `<CharacterScreen key={characterId} characters={characters} characterId={characterId} sessions={sessions} />`
  (reflowed onto several lines; `params.id ?? ""` and the keying are unchanged).

`frontend/src/app/App.tsx` — **changed**.

- `export type AppProps` — **unchanged**
  (`{ user: CurrentUser; storage: LayoutStorage | null }`). The
  `const [sessions] = useState(() => new SessionsState());` line and the `sessions={sessions}`
  on `WorkspaceShell` are step 006's and were not touched.
- Exactly two prop additions, nothing else in the file changed (both route elements reflowed
  onto several lines):
  - `/characters/new` →
    `<CharacterScreen characters={characters} characterId={null} sessions={sessions} />`
  - `/characters/:id` → `<CharacterRoute characters={characters} sessions={sessions} />`
- `/sessions/:id` is still `element={null}` — **step 009's** replacement, deliberately not
  touched here. The other four routes, the catch-all and `WorkspaceShell` are untouched.

Gate after the freeze, from `frontend/`: `npm run typecheck`
(`tsc --noEmit -p tsconfig.json && tsc --noEmit -p tsconfig.node.json`). **Every file under
`src/` compiles clean — this step's three files produce no error** — and the
`tsconfig.node.json` pass is clean (run separately, exit 0, because the `&&` short-circuits).
Four errors remain, **all four in test files the test-coder owns and this step did not touch**:

- **New — this step's expected fallout** (DoD-16, harvest E19; missing required `sessions`):
  - `tests/app/CharacterScreen.test.tsx(307,25)` TS2741 — the `/characters/new` render passes
    `{ characters, characterId: null }`, missing `sessions` from `CharacterScreenProps`;
  - `tests/app/CharacterScreen.test.tsx(309,53)` TS2741 — the `/characters/:id` render passes
    `{ characters }`, missing `sessions` from `CharacterRouteProps`.
- **Pre-existing — from step 006's freeze**, unchanged by this step:
  - `tests/app/CharacterTree.test.tsx(186,12)` TS2739 — missing `sessions`, `storage`;
  - `tests/app/WorkspaceShell.test.tsx(186,10)` TS2741 — missing `sessions`.

`tests/app/App.test.tsx`, `tests/app/AppBoot.test.tsx` and `tests/entries.test.tsx` **typecheck
clean** (they mount `App`, whose props did not change); their amendments are runtime-only — each
character-screen `fetch` stub must answer `GET /api/characters/<id>/sessions` and tolerate a
**second** `GET /api/characters/<id>/setups` (harvest E19, `008.context.md`), which is invisible
to `tsc` and is the test-coder's work. No test file was touched by this step. `npm test` was
deliberately not run (verifier-only). A direct scan of all three files for the
`ids-are-strings` id-colon-number pattern, `parseInt` and any `@mantine/notifications` import
found nothing.

- Caller-compile edits (out of Source-files scope): **None.** The only source call sites of
  `CharacterScreen` / `CharacterRoute` are in `App.tsx`, itself one of this step's Source files;
  no other file under `frontend/src` imports either (`AppBoot.tsx` renders `App`, whose props
  are unchanged). `SessionsSection.tsx` is new and its only source importer is
  `CharacterScreen.tsx`. No file outside the Source list was modified — `SetupsSection.tsx`,
  `sessionsSectionState.ts`, `sessionsState.ts`, `sessionsApi.ts`, `sessionLabel.ts`,
  `characterScreenState.ts`, `CharacterTree.tsx`, `WorkspaceShell.tsx` and
  `shared/IconButton.tsx` are all untouched.

### Step 009 — frozen interface (2026-10-02)

Two **new** frontend modules under `frontend/src/app/` — `sessionScreenState.ts` and
`SessionScreen.tsx` — plus one **existing** file edited in exactly one route element,
`App.tsx`. No existing signature was removed, renamed or widened anywhere: `AppProps` is
unchanged and every other route, `WorkspaceShell` and both character elements are
byte-untouched. Relative imports only, no path aliases (F25). No notification API import
(E21: the one textual mention of `notifyFailure` in `SessionScreen.tsx` is a comment naming
what is deliberately *not* imported, and `conventions.test.ts` strips comments and keys on an
`@mantine/notifications` import, of which there is none). No `parseInt` and no
id-colon-`number`-shaped text in any of the three files, comments included (E21's scan does
**not** strip comments). `characterScreenState.ts` / `CharacterScreen.tsx` (009 steps 006 /
007, harvest C7 / D12) are the template for both new modules.

`frontend/src/app/sessionScreenState.ts` (**new file**). Its only skeleton imports are
`makeAutoObservable` from `mobx` and `import type { Session } from "./sessionsApi";`. The
module is React-free and DOM-free.

- `export type SessionScreenStatus = "idle" | "loading" | "ready" | "not-found" | "failed"`
  — **new**. The literal union is frozen exactly, in this order. `"idle"` is the pre-load
  value (the component loads on mount), which is why this union carries one more member than
  009's `CharacterScreenStatus` (`"loading" | "ready" | "not-found" | "failed"`).
- `export class SessionScreenState` — **new**. **Real, not a stub** — the fields and the
  constructor are the declaration the tests bind to. Fields in declaration order, with these
  types and initial values:
  - `sessionId: string` — assigned from the constructor argument, verbatim, never parsed;
  - `session: Session | null = null` — the last server-returned row (004's `Session`);
  - `status: SessionScreenStatus = "idle"`.

  `constructor(sessionId: string)` — body is exactly
  `this.sessionId = sessionId;` then `makeAutoObservable(this, {}, { autoBind: true });`
  (`charactersState.ts` / `sessionsState.ts`'s call verbatim, empty overrides,
  `autoBind: true`). Unlike `CharacterScreenState`, the constructor does **not** derive the
  status: there is no "new" mode, so `"idle"` is a plain field initialiser.
- `export async function loadSessionScreen(state: SessionScreenState, signal?: AbortSignal): Promise<void>`
  — **new**. The signature is frozen exactly: the state first, the signal **optional, not
  nullable** (`string | undefined` via `?`), returning `Promise<void>` and never rejecting.
  Its contract (body unimplemented): sets `"loading"` first so a Retry from `"failed"` shows
  the loader again; requests the one session by `state.sessionId`; on success writes
  `state.session` plus `"ready"`; an `ApiError` whose `code` is `session_not_found` writes
  `"not-found"`; any other failure, transport included, writes `"failed"`; writes nothing
  once aborted. **Reads only** — no write route is called, so `last_used_at` is untouched
  (D3), and the screen's single source is one `GET /api/sessions/{id}`, never the workspace
  `SessionsState` (an archived session reached by URL is not in that list).
- `const SESSION_NOT_FOUND = "session_not_found";` — **new, module-private, deliberately NOT
  exported.** The backend's 404 code from step 001, frozen by name **and** value. Private for
  `CHARACTER_NOT_FOUND`'s reason (harvest C7): nothing may assert against the constant
  instead of the spec's literal.

`frontend/src/app/SessionScreen.tsx` (**new file**). Skeleton imports: `type * as React` and
`useState` from `react`, `observer` from `mobx-react-lite`, `useParams` from
`react-router-dom`, `import type { CharactersState } from "./charactersState";` and
`SessionScreenState` from `./sessionScreenState`. No Mantine import yet (see the SKELETON
block).

- `export type SessionScreenProps` — **new**. In full, in declaration order, both props
  **required**:
  - `sessionId: string` — the `:id` route parameter verbatim; a string, never parsed.
  - `characters: CharactersState` — the one workspace characters state `App` creates (009
    D11), **read only**: it supplies the character link's text when it already holds that
    character and nothing is fetched when it does not (D17). The screen never writes to it.

  There is deliberately **no** `sessions: SessionsState` prop: this screen must not read the
  workspace sessions list, and no prop should tempt it to.
- `export const SessionScreen` — **new**.
  `observer(function SessionScreen(props: SessionScreenProps): React.JSX.Element)` —
  `CharacterScreen`'s declaration form verbatim. It creates its state once with
  `const [state] = useState(() => new SessionScreenState(props.sessionId));` (never
  `useMemo`).
- `export type SessionRouteProps` — **new**. One required prop, `characters: CharactersState`,
  passed straight through. No `sessionId` prop: the route reads it.
- `export function SessionRoute(props: SessionRouteProps): React.JSX.Element` — **new**, and
  its **body is real, not a stub**, because the keying is interface. Verbatim:

  ```tsx
  const { characters } = props;
  const params = useParams();
  const sessionId = params.id ?? "";

  return <SessionScreen key={sessionId} sessionId={sessionId} characters={characters} />;
  ```

  `params.id ?? ""` is `CharacterRoute`'s form (harvest D12) — the parameter is used verbatim,
  with no `parseInt` and no numeric coercion anywhere. `key={sessionId}` is what makes an
  in-entry move from `/sessions/<a>` to `/sessions/<b>` build a **fresh** `SessionScreenState`
  and a fresh load instead of re-rendering `a`'s header (DoD-9).

**Left unimplemented for the coder — the whole of `SessionScreen`'s render and its load
effect.** The body is `return notImplemented("SessionScreen render", state, characters);`, so
the component **throws when rendered**: nothing is half-built, and no empty or placeholder
centre can accidentally satisfy a DoD assertion (an empty main region is exactly what 008's
route test asserted for this path, so a blank render would be a false pass). A
`SKELETON (011 step 009)` block at the top of the file names each piece as the coder's, with
its exact text from the step file: the `loadSessionScreen` mount effect with an
`AbortController` aborted on unmount (`void`ed from the handler, the same call re-run by
"Retry"); the `"idle"` / `"loading"` centred `Loader`; `"not-found"` → **"Session not found"**
with no retry; `"failed"` → **"Could not load the session"** (D18) plus a **"Retry"** button;
and `"ready"` → the `/characters/<character_id>` link whose text is the character's name when
`characters.characters` holds that id by string equality and otherwise the neutral
**"Character"** (no second request — D17), a heading of
`formatSessionStart(session.created_at)` with **no** zone argument (005), the `setup_name`
when non-null and nothing at all otherwise, an **"Archived"** `Badge` when
`isSessionArchived(session)`, then the line **"No entries yet."**. Named as deliberately
absent, per D5 / D17 / D18: any Archive / Restore / "Actions for …" control, any textbox, any
button at all in the ready centre, any stream, ruler, composer, zone or wall, and any
notification.

Two pieces of **scaffolding the coder deletes**, present only because `noUnusedLocals` /
`noUnusedParameters` fail a declaration nothing reads yet — a compile constraint, **not** a
contract change, exactly as steps 002–008 recorded:

- each file declares the private `function notImplemented(name: string, ...args: unknown[]): never`
  (step 004's helper verbatim), and `loadSessionScreen` / `SessionScreen`'s render return
  through it;
- `sessionScreenState.ts` carries one module-level `void SESSION_NOT_FOUND;` line (step 008's
  `void NO_SETUP_VALUE;` posture) so the frozen constant compiles before the body reads it.

The **imports the coder adds with the bodies** are listed in each file's SKELETON block and
are not signature changes: `runInAction` from `mobx`, `isApiError` from `../shared/apiError`,
`fetchSession` from `./sessionsApi` and the module's own
`isAbortRejection(error) { return error instanceof Error && error.name === "AbortError"; }`
in the state module (A2: an abort propagates **unwrapped**, never as an `ApiError`); and
`useEffect` / `useRef`, `Link`, the Mantine `Anchor` / `Badge` / `Button` / `Center` /
`Container` / `Group` / `Loader` / `Stack` / `Text` / `Title`, `isSessionArchived`,
`formatSessionStart` and `loadSessionScreen` in the component.

`frontend/src/app/App.tsx` — **changed**. Exactly one route element plus its import and one
docblock phrase; nothing else in the file moved.

- `export type AppProps` — **unchanged** (`{ user: CurrentUser; storage: LayoutStorage | null }`).
- The `/sessions/:id` route, **was** `<Route path="/sessions/:id" element={null} />`, **now**
  exactly:

  ```tsx
  <Route path="/sessions/:id" element={<SessionRoute characters={characters} />} />
  ```

  with the new value import `import { SessionRoute } from "./SessionScreen";` placed after the
  `CharacterScreen` import. `characters` is the same `CharactersState` instance the tree and
  the character screen already receive — **no** `sessions={sessions}` is passed (this screen
  must not read the workspace list), and `const [sessions] = useState(() => new SessionsState());`
  and `sessions={sessions}` on `WorkspaceShell` (step 006's) are untouched.
- **Every other route is unchanged**: `/` and `/settings` and `/search` are still
  `element={null}`, `/characters/new` and `/characters/:id` still carry step 008's props, and
  `*` still renders `<Text p="md">Page not found</Text>`.
- One docblock phrase was corrected (011 no longer "fills a remaining centre later" — it fills
  `/sessions/:id` now). No other line changed.

Gate after the freeze, from `frontend/`: `npm run typecheck`
(`tsc --noEmit -p tsconfig.json && tsc --noEmit -p tsconfig.node.json`). **Every file under
`src/` compiles clean — this step's three files produce no error** — and the
`tsconfig.node.json` pass is clean (run separately, exit 0, because the `&&` short-circuits).
The **same four errors as after step 008 remain, all four pre-existing, all in test files the
test-coder owns, none touched or caused by this step**:

- `tests/app/CharacterTree.test.tsx(186,12)` TS2739 — missing `sessions`, `storage` (step 006);
- `tests/app/WorkspaceShell.test.tsx(186,10)` TS2741 — missing `sessions` (step 006);
- `tests/app/CharacterScreen.test.tsx(307,25)` TS2741 — missing `sessions` (step 008);
- `tests/app/CharacterScreen.test.tsx(309,53)` TS2741 — missing `sessions` (step 008).

`tests/app/App.test.tsx`, `tests/app/AppBoot.test.tsx` and `tests/entries.test.tsx`
**typecheck clean** (they mount `App`, whose props did not change). Their step-009 amendments
are **runtime-only and invisible to `tsc`**, and they are the test-coder's work (DoD-11,
DoD-12): `App.test.tsx`'s `EMPTY_CENTRE_ROUTES` literal must drop `/sessions/1` (harvest E17)
and its stubs must answer `GET /api/sessions/1` by exact path, and `entries.test.tsx`'s
`stubAppIdentity` must answer `GET /api/sessions/abc123` (harvest E18, any status) now that
`/sessions/abc123` mounts a real element. No test file was touched by this step. `npm test`
was deliberately **not** run (verifier-only). A direct scan of all three source files for
`\b\w*(?:id|Id)\s*\??\s*:\s*number\b`, `parseInt`, `Number.parseInt` and any
`@mantine/notifications` import found nothing.

- Caller-compile edits (out of Source-files scope): **None.** Both new modules' only source
  importer is `App.tsx`, itself one of this step's Source files; `AppBoot.tsx` renders `App`,
  whose props are unchanged. No file outside the Source list was modified — `sessionsApi.ts`,
  `sessionsState.ts`, `sessionLabel.ts`, `treeCollapse.ts`, `sessionsSectionState.ts`,
  `SessionsSection.tsx`, `CharacterScreen.tsx`, `CharacterTree.tsx`, `WorkspaceShell.tsx`,
  `charactersState.ts`, `characterScreenState.ts` and every backend file are untouched, and no
  signature of an existing symbol changed.

## Tests

### Step 001 — tests (2026-10-02)

- `backend/tests/test_sessions_models.py` (**new**) — covers DoD-5, DoD-6, DoD-7, DoD-8:
  - DoD-5 (4 tests) — `SessionNotFoundError` is a `DomainError` subclass; `code =
    "session_not_found"` / `http_status = 404` as class attributes; empty `detail`; raised
    from a route on a throwaway app with `register_exception_handlers` it answers **404**
    with the envelope `{"error": {"code": "session_not_found", "message": …, "detail": {}}}`.
  - DoD-6 (4 tests, one shared with DoD-5) — the same four for `SetupArchivedError` with
    `code = "setup_archived"` / **409** / empty `detail`, plus one test that the two new
    codes and statuses are distinct.
  - DoD-7 (8 tests) — all three ids serialise as decimal strings (small and snowflake-sized);
    `setup_id` / `setup_name` / `archived_at` `None` → JSON `null`; a set `setup_name` and
    `archived_at` pass through; exactly the eight wire keys and never `user_id`; no
    `title` / `partner_label` / `model_ref` / `status` field or key; the three timestamps pass
    through; `SessionListResponse` has only the key `sessions`, keeps the given order, and
    serialises the empty list.
  - DoD-8 (6 tests) — `{}` → `setup_id is None` with `model_fields_set == set()`;
    `{"setup_id": null}` → the same; `{"setup_id": "7250000000000000001"}` → the int
    `7250000000000000001`; a non-numeric `setup_id` (`"abc"`, `"7a"`, `""`) raises
    `ValidationError`; `character_id` / `user_id` / `last_used_at` / `title` / a nonsense key
    are **ignored, not rejected** and none appears on the parsed model, both alongside a real
    `setup_id` and on an otherwise empty body.
- `backend/tests/test_db_schema.py` (**existing, 011 delta appended**) — covers DoD-1, DoD-2,
  DoD-3, DoD-4, DoD-9:
  - DoD-1 (3 tests) — `sessions` is in `schema.metadata.tables`; the delta
    `set(tables) - PRE_011_TABLES - LATER_THAN_011_TABLES == NEW_011_TABLES` in 009/010's
    later-table-proof shape (`PRE_011_TABLES = PRE_010_TABLES | NEW_010_TABLES`,
    `NEW_011_TABLES = {"sessions"}`, `LATER_THAN_011_TABLES: set[str] = set()`); every
    pre-011 table still registered; and the "survives a table a later feature declares"
    guard modelled on `test_the_010_delta_survives_a_table_a_later_feature_declares`.
  - DoD-2 (4 tests, two parametrized) — exactly the eight columns; `id` alone is the primary
    key; `setup_id` and `archived_at` nullable; the other six NOT NULL; none of `title`,
    `partner_label`, `rp_language`, `preferred_language`, `model_ref`, `system_prompt`,
    `tools`, `status`, `state` declared.
  - DoD-3 (5 tests) — the three FK targets (`users.id`, `characters.id`, `setups.id`);
    `setup_id` declares neither a `server_default` nor a `default`; **exactly one** index,
    non-unique, columns exactly `["user_id", "character_id"]` in that order.
  - DoD-4 (5 tests) — a file-local `_seeded_sessions_connection` runs
    `metadata.create_all` on a fresh `db_engine` file, turns `PRAGMA foreign_keys = ON` and
    asserts it reads back `1` (so enforcement is proved, not assumed), then commits owner
    `id=1`, character `id=10` and setup `id=20`. `sessions` appears in `sqlite_master`; a row
    with `setup_id` NULL inserts; a row naming the existing setup inserts and reads back
    `20`; and a bad `character_id`, a bad `setup_id` and a bad `user_id` each raise
    `IntegrityError`. **No shared fixture was added to `conftest.py`.**
    - **Rename (red-gate repair, 2026-10-02)** — the raw-insert pair this delta added was first
      named `RAW_SESSION_INSERT` / `_raw_session`, which are the names feature 004 already owns
      at module scope for the **`auth_sessions`** table (near the top of the file). Being
      module-level, the later definitions shadowed 004's for the whole module and three
      004-authored tests began inserting into `sessions`. The 011 pair is now named for its
      table — **`RAW_SESSIONS_INSERT`** and **`_raw_sessions_row`** — and all five references
      inside 011's own DoD-4 tests were updated. Feature 004's original
      `RAW_SESSION_INSERT` / `_raw_session` are **untouched**. No assertion changed.
  - DoD-9 (4 tests, plus three one-line edits) — `"sessions"` was appended to
    `LATER_THAN_006_TABLES`, `LATER_THAN_009_TABLES` (which already held `"setups"`) and
    `LATER_THAN_010_TABLES` (previously empty), so 006's, 009's and 010's existing delta
    assertions keep meaning what they meant. **No existing assertion was changed** — only
    those three later-features sets and their comments. 011-authored tests re-assert each of
    the three deltas with `sessions` registered and assert that each earlier later-features
    set now names `"sessions"` while `PRE_011_TABLES` does not. The two 006-authored
    registry-literal guard tests walk `metadata.tables` generically and needed **no edit**.
- `backend/tests/test_admin_db_router.py` — **no edit made.** Read and verified: its
  `UNDECLARED_NAMES` list holds `"no_such_table"`, `"legacy_notes"`, `"sqlite_master"` and the
  injection-shaped names, and **does not contain `"sessions"`** (010/001 DoD-9 already ended
  the swap chain). DoD-10's conditional branch therefore did **not** fire; its
  undeclared-name 404 `unknown_table` expectations hold unchanged with `sessions` registered.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
  DoD-9 ✓, DoD-10 ✓ (verified-no-change, per the step's own "nothing changes" branch),
  DoD-11 **[manual/live, no test — uncovered by design]** (the admin Database page listing
  `sessions` as missing on a pre-011 database and **Create** bringing it in-sync requires a
  live run).
- Tests were **not** run — the red gate is the verifier's.

### Step 002 — tests (2026-10-02)

- `backend/tests/test_sessions_service.py` (**new**, 38 tests) — covers DoD-1 … DoD-16.
  File-local fixtures only (**nothing added to `conftest.py`**): an `engine` fixture that
  runs `schema.metadata.create_all` on `db_engine` and raw-seeds the FK chain — two users
  (`USER_A`, `USER_B`), four characters (two of A's, one **archived** of A's, one of B's)
  and four setups (A's under `CHAR_A1`, A's **archived** under `CHAR_A1`, A's under
  `CHAR_A2`, B's under `CHAR_B1`) — plus a real `SnowflakeGenerator` `generator` fixture, a
  file-local `_FixedIdGenerator`, thin per-call wrappers each opening their own
  `engine.connect()`, and direct row-count / raw-row-state helpers.
  - DoD-1 (3 tests) — `start_session` with the `setup_id` argument **omitted** returns the
    `_FixedIdGenerator`'s id, that `character_id`, `setup_id` / `setup_name` /
    `archived_at` `None`, and `created_at == updated_at == last_used_at`, each matching
    `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$` (shape, never a hard-coded
    instant); an explicit `None` behaves the same; `get_session` returns an **equal** value
    and both listings contain it.
  - DoD-2 (2 tests) — a start with A's setup under the same character returns that
    `setup_id` and `setup_name == SETUP_A1_NAME`; a second session with the same setup
    succeeds and both rows list with that `setup_id` and `setup_name`.
  - DoD-3 (4 tests, two parametrized over another user's / nobody's character id) —
    `start_session` and both per-character listings raise `CharacterNotFoundError`; the
    `sessions` row count is unchanged after the refusal (also against an already-populated
    table); start and both per-character listings succeed under A's **archived** character.
  - DoD-4 (1 test, parametrized three ways) — another user's setup, a setup that exists for
    nobody, **and A's own setup under A's other character** each raise
    `SetupNotFoundError` with the `sessions` count unchanged.
  - DoD-5 (1 test) — A's **archived** setup under that character raises
    `SetupArchivedError` (not `SetupNotFoundError`) with the `sessions` count unchanged.
  - DoD-6 (2 tests) — two users each with sessions (one archived each): `list_sessions`
    returns only the caller's and `list_character_sessions` only the addressed character's
    (A's other character excluded), with and without `include_archived`.
  - DoD-7 (2 tests) — three **raw-inserted** rows whose `last_used_at` (May / March /
    January) disagrees with their `created_at` order come back `last_used_at` descending
    from all four listing forms, and explicitly **not** in creation-descending order; three
    sessions started through `start_session` come back newest first.
  - DoD-8 (2 tests) — both listings exclude the archived row by default and carry both
    states with the flag.
  - DoD-9 (2 tests) — `get_session` / `archive_session` / `restore_session` on another
    user's session (both a working and an archived one) and on an id that exists for nobody
    raise `SessionNotFoundError`, with the stored `(archived_at, last_used_at,
    updated_at)` read raw and asserted unchanged afterwards.
  - DoD-10 (3 tests) — archive returns `archived_at` in the fixed-width form, the row is
    absent from both default listings, present in both include-archived listings and still
    returned by `get_session`; a second archive returns the same `archived_at` **and**
    `updated_at`; `last_used_at` is unchanged throughout.
  - DoD-11 (2 tests) — restore returns `archived_at` `None`, the row is back in both
    default listings, and its `id`, `character_id`, `setup_id`, `setup_name`, `created_at`
    and `last_used_at` equal the pre-archive values; restoring a working session leaves
    `updated_at` (and the whole value) untouched.
  - DoD-12 (1 test) — after `get_session` and all four listing forms, the raw
    `last_used_at` and `updated_at` are byte-identical to the pre-read values.
  - DoD-13 (1 test) — after a **raw update** of `setups.archived_at`, `get_session` and all
    four listing forms still return the session's `setup_id` and `setup_name`.
  - DoD-14 (5 tests) — on the **same** connection, after `list_sessions`,
    `list_character_sessions`, `get_session`, and after each of the two raising exits
    (`CharacterNotFoundError` from the per-character listing, `SessionNotFoundError` from
    the get), a following `connection.begin()` succeeds and is rolled back.
  - DoD-15 (2 tests) — after a start with no setup the `setups` count is unchanged while
    `sessions` grows by exactly one; the reads, the archive and the restore add no row to
    either table.
  - DoD-16 (3 tests) — a source-text scan of `app/services/sessions.py` via
    `inspect.getsource`: no `delete(` call, no `DELETE` SQL keyword, no `delete from`, no
    `fastapi` import; an `ast` walk finding no import from `app.services` (absolute or
    relative); and no `model_ref` anywhere in the text. This trio is expected to be
    **green against the stub** — it is a constraint scan, not a behaviour test.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
  DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓. No
  `[manual/live]` item in this step.
- Tests were **not** run — the red gate is the verifier's.

### Step 003 — tests (2026-10-02)

- `backend/tests/test_sessions_router.py` (**new**, 27 test functions / 48 parametrized
  cases) — covers DoD-1 … DoD-17. File-local fixtures only (**nothing added to
  `conftest.py`**), in `test_setups_router.py`'s shape (harvest F23): `_insert_user` +
  `_seed` raw-inserting the two roleplayers, an `engine` fixture over conftest's `db_engine`,
  an `application` fixture building `create_app()` with `dependency_overrides[get_settings]`,
  an autouse `_quiet_factory_logging`, and `_login_token` / `_as` / `_player_a` /
  `_player_b` / `_anonymous` giving **a fresh `TestClient` per caller with never-shared
  cookies**. The FK chain is built through the real routes: `_character` (009's
  `POST /api/characters`), `_create_setup` (010's `POST /api/characters/{id}/setups`),
  `_archive_setup` (`POST /api/setups/{id}/archive`), `_archive_character`
  (`POST /api/characters/{id}/archive`). Every path helper builds an **exact** path
  (`/api/sessions`, `/api/sessions/<id>`, `/api/characters/<id>/sessions`,
  `/api/characters/<id>/setups`) — never a prefix. "Nobody's" ids are the large decimal
  strings `7250000000000000001..3`. A module-level `_OMITTED` sentinel distinguishes "send
  **no body at all**" from "send this JSON body".
  - DoD-1 (1 test, parametrized over all six routes) — anonymous `GET /api/sessions`,
    `GET`/`POST /api/characters/<id>/sessions`, `GET /api/sessions/<id>`,
    `POST …/archive`, `POST …/restore` each answer 401 `not_authenticated` in the
    `{"error": {...}}` envelope.
  - DoD-2 (3 tests, one parametrized three ways) — `{}` answers 201 with the eight wire
    keys and no `user_id`, `id` / `character_id` decimal-digit **strings**, `character_id`
    equal to C's id string, `setup_id` / `setup_name` / `archived_at` null and
    `last_used_at == created_at`; the created row reads back **equal** from
    `GET /api/sessions/<id>` and its id appears in both listings; and all three no-setup
    shapes — **no body at all**, `{}`, `{"setup_id": null}` — answer 201 with `setup_id`
    null.
  - DoD-3 (2 tests) — `{"setup_id": "<S>"}` answers 201 with `setup_id` equal to S's id
    string and `setup_name` equal to S's name; a second session with the same setup answers
    201 with a different id and C's listing shows both rows with that `setup_id` /
    `setup_name`.
  - DoD-4 (2 tests, parametrized) — a setup under another of the caller's characters,
    another user's setup, and a setup id that exists for nobody each answer 404
    `setup_not_found` with `detail == {}` and leave C's `include_archived=true` listing
    **byte-equal** to the pre-request listing; and the "other character" / "other user"
    bodies are asserted **equal to the nobody's-id body**.
  - DoD-5 (1 test) — after `POST /api/setups/<S>/archive`, `{"setup_id": "<S>"}` answers
    409 `setup_archived` with `detail == {}` and C's listing is unchanged.
  - DoD-6 (3 tests, two parametrized GET/POST) — as B, both routes on A's character answer
    404 `character_not_found` with `detail == {}`; the **bodies are equal** to those for a
    character id that exists for nobody; and after B's refused POST, A's per-character and
    all-sessions `include_archived=true` listings are unchanged.
  - DoD-7 (2 tests, each parametrized over GET / archive / restore) — as B, all three answer
    404 `session_not_found` with `detail == {}`, A's session reads back **equal** to the
    created row, and the **bodies equal** those for a session id that exists for nobody.
  - DoD-8 (2 tests, each parametrized default / `include_archived=true`) — with A owning two
    characters (one session each plus one archived) and B one, A's `GET /api/sessions` holds
    exactly A's ids (the archived one only with the flag) and never B's, B's holds only its
    own, and A's per-character listing holds only that character's.
  - DoD-9 (2 tests) — archive answers 200 with `archived_at` a string in the Wire contract's
    fixed-width form, the id leaves both default listings, is present in both
    `include_archived=true` listings and still reads by id; archiving again answers the
    **same** `archived_at`, and `last_used_at` equals the created value throughout.
  - DoD-10 (1 test) — on a session started **with** a setup: restore answers 200 with
    `archived_at` null, the id is back in both default listings, and the read-back row's
    `id`, `character_id`, `setup_id`, `setup_name`, `created_at` and `last_used_at` equal the
    pre-archive values.
  - DoD-11 (2 tests) — three sessions started in sequence under C come back
    `[third, second, first]` from **both** `GET /api/characters/<C>/sessions` and
    `GET /api/sessions`; four sessions started alternately under two characters come back
    from `GET /api/sessions` in exact reverse start order regardless of character (relies on
    D3: no content writes yet, so last use equals start order).
  - DoD-12 (1 test) — two `GET /api/sessions/<id>` calls return the created
    `last_used_at` and `updated_at` unchanged.
  - DoD-13 (1 test) — `DELETE /api/sessions/<id>`, `DELETE /api/sessions`,
    `DELETE /api/characters/<C>/sessions` and `PATCH /api/sessions/<id>` each answer **405
    (status only**, per `003.context.md`), and the session still reads back equal afterwards.
  - DoD-14 (1 test) — after `POST /api/characters/<C>/archive`, listing C's sessions answers
    200, starting a session under C answers 201, `GET /api/sessions/<id>` of the pre-existing
    session answers 200, and that id is still in C's listing.
  - DoD-15 (1 test) — after `POST /api/setups/<S>/archive`, the session's
    `GET /api/sessions/<id>` and both listings still carry its `setup_id` and `setup_name`.
  - DoD-16 (2 tests, one parametrized five ways) — `GET /api/sessions/abc`,
    `POST /api/sessions/abc/archive`, `POST /api/sessions/abc/restore`,
    `GET /api/characters/abc/sessions` and `POST /api/characters/abc/sessions` each answer
    422 (signed in, so the router-level 401 does not pre-empt it); a start with
    `{"setup_id": "abc"}` answers 422 and leaves C's listing unchanged.
  - DoD-17 (1 test) — with this router registered, `GET /api/characters/<C>`,
    `GET /api/characters/<C>/setups` and `POST /api/characters/<C>/archive` each answer 200.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
  DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓,
  DoD-17 ✓, DoD-18 **[manual/live, no test — uncovered by design]** (a dev backend whose
  database pre-dates 011, the administrator pressing **Create** for `sessions`, and `curl`
  against it requires a live run).
- Tests were **not** run — the red gate is the verifier's.

### Step 004 — tests (2026-10-02)

Two **new** Vitest files, bound to `### Step 004 — frozen interface`. Both import every
Vitest symbol explicitly (`globals: false`, harvest F23), stub `fetch` per test with
`vi.stubGlobal` and key every assertion on the **exact pathname plus query string**, never a
prefix. Every fixture id is past `Number.MAX_SAFE_INTEGER`, and every session fixture's
`last_used_at` order is deliberately the **reverse** of its id order (harvest E20), so an
accidental id sort or a numeric coercion is caught. Neither file imports 009 or 010:
`orderCharactersByUse` is exercised with plain `{ id, label }` objects through its generic.

- `frontend/tests/app/sessionsApi.test.ts` (**new**, 24 tests) — covers DoD-1, DoD-2, DoD-3.
  `setupsApi.test.ts`'s helper shape (`seen` → `{ method, path, search }`, `sentBody`,
  `bodyKeys`, `envelope`, `rejection`).
  - DoD-1 (10 tests) — `fetchSessions(false)` is exactly `GET /api/sessions` with
    `search === ""`; `fetchSessions(true)` exactly `?include_archived=true`;
    `fetchCharacterSessions("7250000000000000001", false)` exactly
    `GET /api/characters/7250000000000000001/sessions` with no query string, and with `true`
    the one flag; both unwrap the payload's `sessions` array in the payload's order; an empty
    listing resolves to `[]`; and every `id` / `character_id` / `setup_id` comes back as the
    identical string (or `null`) the payload carried, with `typeof` pinned to `"string"`.
  - DoD-2 (8 tests) — `fetchSession` GETs exactly `/api/sessions/<id>` (archived rows
    included) and resolves to the response's session; `startSession(characterId, null)` POSTs
    `/api/characters/<id>/sessions` with the parsed body `{ setup_id: null }` and
    `bodyKeys === ["setup_id"]` (a missing or extra key fails), and with an id exactly
    `{ setup_id: "7250000000000000009" }`, the id still a string; `archiveSession` /
    `restoreSession` POST `/api/sessions/<id>/archive` / `/restore` and resolve to the
    session; a large id reaches each id-addressed route unchanged.
  - DoD-3 (6 tests) — a 404 `session_not_found` envelope rejects `fetchSession` (and
    `archiveSession` / `restoreSession`) with an `ApiError` whose `.code` is
    `session_not_found` and `.status` 404; a 409 `setup_archived` envelope rejects
    `startSession` with `.code` `setup_archived` / `.status` 409; a 404
    `character_not_found` rejects the character-addressed calls; `isSessionArchived` is true
    for a string `archived_at` and false for `null`.
- `frontend/tests/app/sessionsState.test.ts` (**new**, 47 tests) — covers DoD-4 … DoD-9.
  `charactersState.test.ts`'s posture (`deferred`, `flush`, `snapshot`, `withSessions`).
  - DoD-4 (12 tests) — a fresh `SessionsState` is `{ sessions: [], status: "idle" }`;
    `loadSessions` is `"loading"` while pending (first load and reload) and `"ready"` after;
    it requests exactly `GET /api/sessions` with **no** query string; it writes exactly the
    server's rows, keeping an order that is not the `last_used_at` order; an empty listing is
    ready with no rows; an error envelope and a transport rejection each set `"failed"`, keep
    the previous rows and resolve without throwing; and with its signal aborted before the
    response settles (both an aborting `fetch` and a late success) the whole snapshot is
    **identical to the pre-abort snapshot** and the call resolves.
  - DoD-5 (8 tests) — an absent working row lands first when newer than all, between two
    rows when between them, last when older than all, **after** an equal-`last_used_at` row
    (the tied fixture's id is deliberately higher, so an id tie-break would fail), and alone
    in an empty list; a present row with unchanged `last_used_at` keeps its index carrying
    the new values (first, middle and last cases).
  - DoD-6 (7 tests) — an archived row removes that id when present (middle and first),
    leaves the rows unchanged when absent, is **not** inserted even when most recently used,
    leaves an empty list empty; applying the restored working version puts the row back at
    its `last_used_at` position.
  - DoD-7 (5 tests) — only that character's sessions, in the given order (including a
    scrambled given order), `[]` for a character with none and for an empty list, and the
    same over the state's own observable rows.
  - DoD-8 (8 tests) — the step's exact example: `[A, B, C]` given, C's session the most
    recent, A's older, B none → `[C, A, B]`; no sessions at all → the given order; two
    session-less characters keep their relative given order (three given orders); a
    character is ranked by the **greatest** `last_used_at` among its sessions (a min would
    invert the pair); equal greatest values keep the given order (stability, both
    directions); sessions of characters not in the list are ignored; **neither input is
    mutated** and the result is a different array holding the same objects.
  - DoD-9 (7 tests) — an `autorun` reading `sessions` re-runs after `applySession` (insert
    and archived-removal) with the new ids; one reading `status` re-runs after
    `loadSessions` settles `"ready"` and after it fails `"failed"`; `sessions` and `status`
    are the observable, non-computed fields; the prototype carries only `constructor`; the
    load, the upsert and the derivations are free functions.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
  DoD-9 ✓ — no `[manual/live]` item in this step.
- Tests were **not** run — the red gate is the verifier's.

### Step 005 — tests (2026-10-02)

- `frontend/tests/app/sessionLabel.test.ts` (**new**, 14 tests) — covers DoD-1, DoD-2, DoD-3,
  DoD-4 and the `sessionLabel.ts` half of DoD-10. This file is the **only** place exact
  start-time label values are asserted, and every such clause passes an explicit IANA zone
  (`context.md` Test conventions → "Start-time labels").
  - DoD-1 (2 tests) — `formatSessionStart("2026-10-01T18:05:09.123456+00:00", "UTC")` is
    exactly `"2026-10-01 18:05"`, and that label matches
    `/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/` (no seconds, no zone suffix).
  - DoD-2 (2 tests) — the same instant in `"Asia/Tokyo"` is `"2026-10-02 03:05"` (the date
    rolls over) and in `"America/New_York"` is `"2026-10-01 14:05"`.
  - DoD-3 (3 tests) — `"2026-01-05T03:04:00.000000+00:00"` → `"2026-01-05 03:04"`
    (zero-padded); `"2026-01-05T23:59:59.999999+00:00"` → `"2026-01-05 23:59"` (no rounding
    up to the next minute); `"2026-01-05T00:00:00.000000+00:00"` → `"2026-01-05 00:00"`
    (hour `00`, never `24`).
  - DoD-4 (6 tests, two parametrized over three instants) — the **zone-less** result matches
    `/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/` and equals the result for
    `Intl.DateTimeFormat().resolvedOptions().timeZone`. No local-time string is hard-coded,
    so the suite passes in any zone.
  - DoD-10 (7 tests, six parametrized) — a source scan: `src/app/sessionLabel.ts` is read
    from disk by path, comments stripped (008's `entryIsolation.test.ts` idiom), and must
    reference no `window`, `document`, `localStorage`, `sessionStorage`, React import or
    MobX import. One test asserts the scan actually read a non-empty file.
- `frontend/tests/app/treeCollapse.test.ts` (**new**, 44 tests) — covers DoD-5 … DoD-9 and
  the `treeCollapse.ts` half of DoD-10. All storages are **file-local fakes** built against
  `LayoutStorage`'s shape (`{ getItem(key): string | null; setItem(key, value): void }`,
  declared locally); 008's helpers are not imported and jsdom's `localStorage` is never used.
  - DoD-5 (6 tests) — `TREE_COLLAPSED_KEY === "rphelper.tree-collapsed"`;
    `readCollapsedCharacters` returns `[]` and never throws for a `null` storage, a storage
    with no value under the key, a storage holding only `rphelper.workspace-layout`, and a
    storage whose `getItem` throws.
  - DoD-6 (18 tests, 14 parametrized) — `[]` for unparseable JSON, an empty string, an
    object, a string, a number, `null` and a boolean (each also asserted never to throw);
    the step's exact filtering case
    `["7250000000000000001", 5, "7250000000000000002", "7250000000000000001", null]` →
    exactly `["7250000000000000001", "7250000000000000002"]` (non-strings **dropped, not
    converted**, duplicates dropped, first-seen order kept), plus an all-non-string array and
    an empty array; and the read asks for the single key `rphelper.tree-collapsed` and no
    other (the fake's `getItem` keys are recorded and the distinct set asserted), both with a
    value present and with none.
  - DoD-7 (6 tests) — `writeCollapsedCharacters(storage, ["a", "b"])` makes exactly one
    `setItem` call, keyed `rphelper.tree-collapsed`, whose stored JSON parses to
    `["a", "b"]`; a following `readCollapsedCharacters` returns `["a", "b"]`; the recorded
    `setItem` keys never include `rphelper.workspace-layout` and their distinct set is exactly
    `["rphelper.tree-collapsed"]`; a pre-seeded workspace-layout value is left byte-identical;
    a write **replaces** the whole previously stored set; the empty set round-trips.
  - DoD-8 (4 tests) — `writeCollapsedCharacters` returns normally for a storage whose
    `setItem` throws, for a storage whose `getItem` throws, and for a `null` storage (with
    and without an empty set).
  - DoD-9 (6 tests) — `toggleCollapsedCharacter(["a"], "b")` is `["a", "b"]`;
    `(["a", "b"], "a")` is `["b"]`; after an add and after a removal the **input array is
    unchanged** and the result is a different array object; toggling the same id twice
    returns the original set; an add to the empty set yields `["a"]` leaving the input empty.
  - DoD-10 (7 tests, six parametrized) — the same source scan over
    `src/app/treeCollapse.ts`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
  DoD-9 ✓, DoD-10 ✓ (both source files) — no `[manual/live]` item in this step.
- No source file was read for behaviour. The two new modules were read **only** as raw text
  by DoD-10's scan, which is what that DoD asks for.
- Tests were **not** run — the red gate is the verifier's.

### Step 006 — tests (2026-10-02)

Five test files, all **amended** (no new file): the three component files gain 011's clauses,
the two boot files are stub widening only. Every `it` title ends `— DoD-N` of **this** step.
No source file was read: the bindings come from `## Skeleton` → "Step 006 — frozen interface"
(`CharacterTree`'s required `sessions` / `storage`, `WorkspaceShell`'s required `sessions`) and
from steps 004 / 005' records (`SessionsState`, `applySession`, `TREE_COLLAPSED_KEY`).

**`frontend/tests/app/CharacterTree.test.tsx`** — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5,
DoD-6, DoD-7, DoD-8, DoD-9, DoD-13 (20 new tests in 8 new `describe` blocks).

- Fixtures added: a third character `THEA` ("Thea Brightwater"), so the characters payload is
  `A, B, C` = Corvin Hale, Aria Vance, Thea Brightwater; five `Session` rows built by a local
  `session()` helper, every id past `Number.MAX_SAFE_INTEGER` and `created_at` deliberately
  ordered differently from `last_used_at`. `SESSIONS_PAYLOAD` is server order
  (`last_used_at DESC`): C's session, A's newer (setup `"Tavern"`), A's older (no setup).
- DoD-1 (2 tests) — the payload order A, B, C renders as **C, A, B**; the session-less
  character is last and carries no "Sessions of …" list.
- DoD-2 (2 tests) — `sessionHrefsUnder("Corvin Hale")` is exactly
  `["/sessions/<A-new>", "/sessions/<A-old>"]` (ids verbatim) and Thea's is C's alone; no
  session of another character appears under a character, and the tree holds exactly the three
  payload rows.
- DoD-3 (3 tests) — the `setup_name` `"Tavern"` row shows `"Tavern"`; the `setup_id`-null row's
  whole trimmed text matches `/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/` and holds no setup label; the
  labelled row's text still carries the same shape. **No exact local-time string anywhere, and
  the formatter is never called to compute an expectation.**
- DoD-4 (2 tests) — clicking a session row moves the in-entry router to `/sessions/<id>` with
  `documentNavigation.assign` never called; rendered at `/sessions/<id>`, that row alone has
  `aria-current="page"` — every other session row **and every character row** is asserted not
  to.
- DoD-5 (2 tests) — over an **empty** `fakeStorage()`, each character with sessions carries
  "Collapse <name>" and its rows, and Aria (no sessions) carries **neither** "Collapse Aria
  Vance" nor "Expand Aria Vance"; pressing "Collapse Corvin Hale" hides both A rows, flips the
  label to "Expand Corvin Hale", leaves C expanded, and stores a JSON **array containing A's
  id** under `rphelper.tree-collapsed`.
- DoD-6 (3 tests) — mounted over a storage holding `[A-id]`, A starts collapsed ("Expand A", no
  "Sessions of Corvin Hale" list) and B expanded with its row; "Expand A" restores both rows
  and removes A's id from the stored array; a third test records the fake's `setItem` keys over
  two toggles and asserts **every** written key is `rphelper.tree-collapsed` and that
  `WORKSPACE_LAYOUT_KEY` is neither written nor present.
- DoD-7 (3 tests) — `GET /api/sessions` is requested **exactly once** on mount with an empty
  search (never `include_archived`); turning "Show archived" on takes the characters listing to
  2 requests while the sessions listing stays at 1; the archived character's session row appears
  with it and goes away with it, the working character's row surviving.
- DoD-8 (2 tests) — a sessions listing that fails once shows "Could not load sessions" and a
  "Retry", the three character links still render, "Could not load characters" is absent, no
  session row renders and `.mantine-Notification-root` is empty; "Retry" takes the sessions
  listing to 2 requests and the rows then render.
- DoD-9 (2 tests) — `applySession` on the **passed** state, inside `act`, with no fetch: a new
  session of A with the newest `last_used_at` renders first under A and moves A to the top of
  the character order; the archived version of C's session loses its row while A's survives.
  Both assert the sessions-request count is unchanged.
- DoD-13 (1 test) — explicit: with an empty sessions payload the characters keep the payload
  order, no session row exists, no expand/collapse control exists, and the tree's button-name
  set is exactly `["New character", "Search"]`.

Amendments to 009's clauses in this file, and the form each was kept in:

- `renderTree` now takes `sessions` (fresh `SessionsState`) and `storage` (`null` by default),
  and passes both — this is the fix for the frozen interface's expected
  `CharacterTree.test.tsx(186,12)` TS2739.
- `serveListing(working, archived, sessions = [])` answers `GET /api/sessions` by **exact**
  pathname; `sessionsRequests(calls)` is keyed on `/api/sessions` exactly, never a prefix.
- **009 DoD-1**'s "requests the listing once" clause: `expect(calls).toHaveLength(1)` became
  `expect(sessionsRequests(calls)).toHaveLength(1)` + `expect(calls).toHaveLength(2)`. The
  clause's meaning — one characters listing, nothing unexpected — is preserved exactly; it is
  now two listings because 011 adds the second effect. Its row-order assertion is unchanged and
  runs with an empty sessions payload (DoD-13's form).
- **009 DoD-6**'s two landmine clauses — "the ready tree's only buttons are Search and New
  character" and "no row carries an expand or collapse control" — are **kept verbatim**, both
  rendered with `serveListing`'s **empty** sessions payload, which is exactly the form 011
  DoD-13 requires. A block comment above the `describe` records that, and names 011's DoD-5 /
  DoD-6 / DoD-2 as where the sessions-present behaviour lives. Nothing was deleted.
- **009 DoD-5**'s three characters-failure clauses: their stubs now answer `GET /api/sessions`
  with an empty success, so the tree has exactly **one** "Retry" and `treeButton(/^retry$/i)`
  stays unambiguous. The transport-failure clause rejects the characters path only. No
  assertion changed.
- New queries added so the two tree levels are told apart by `href` rather than by structure:
  `characterLinks` / `characterTexts` (`/characters/…`) and `sessionLinks` / `sessionRow` /
  `sessionHrefsUnder` (`/sessions/…`), plus `querySessionsListFor` ("Sessions of <name>") and
  `chevron(name, "collapse" | "expand")`.

**`frontend/tests/app/WorkspaceShell.test.tsx`** — covers DoD-10 (3 tests).

- `renderShell` now passes `sessions={new SessionsState()}` — the fix for the frozen
  interface's expected `WorkspaceShell.test.tsx(186,10)` TS2741. `stubCharactersFetch(sessions
  = [])` answers `GET /api/sessions` by exact pathname **before** its reject-everything-else
  branch; every 008 / 009 clause keeps its original (empty) payload.
- DoD-10 — expanded, the nav holds "Collapse tree", the "Show archived" switch, the
  "Characters" list, the "User menu" trigger **and** the stubbed session row (by its
  `/sessions/<id>` href); collapsed, `expectRail()` still holds and the rail shows **no**
  session rows; a third clause re-asserts the centre text and the two-child grid beside the
  session rows, so 008's DoD-1 / DoD-9 shape is explicitly unbroken.
- No 008 or 009 assertion was changed. The "writes nothing to the storage" clauses (008 DoD-6,
  DoD-7) still hold: reading the collapsed set writes nothing, and the chevron's label is
  "Collapse <name>", never the anchored `/^collapse tree$/i`.

**`frontend/tests/app/App.test.tsx`** — covers DoD-11 (2 tests).

- `stubWorkspace(rows, sessions = [])` answers `GET /api/sessions` by exact pathname, matched
  first; the two inline `stubFetch` handlers in 009's character-route block each gain the same
  branch (the `/characters/new` one previously rejected every other URL). `listRequests` stays
  keyed on the exact `/api/characters`, so 009 step 008 DoD-8's "no list request after the
  create" is untouched. **No 009 or 010 assertion was dropped or weakened.**
- `EMPTY_CENTRE_ROUTES` was **left alone**, `/sessions/1` included — removing it is step 009's
  edit, and in this step the centre at that route is still empty.
- DoD-11 — at `/` the stubbed session renders as a row under its character in the nav, with
  exactly one characters listing and one sessions listing; a second clause asserts the main
  region's text is still `""` while the tree carries the session row.

**`frontend/tests/app/AppBoot.test.tsx`** — covers DoD-12 (1 test). Stub widening only:
`stubSequence` gains an unconditional empty-list branch for `GET /api/sessions` (without it the
request would hang forever on its fallback). One added clause asserts the boot outcome is
unchanged — the shell nav, the "User menu" trigger, no boot screen, no document navigation —
**and** that the sessions listing was requested once. No existing assertion changed.

**`frontend/tests/entries.test.tsx`** — covers DoD-12 (1 test). Stub widening only:
`stubAppIdentity` gains a `GET /api/sessions` branch before its reject-as-`TypeError` fallback,
and now records the pathnames it saw (`appEntryRequests`, reset per stub install) so the
widening is observable. One added clause asserts the app entry still renders the shell and the
"User menu" into `#root` and that `/api/sessions` was among the requests. The `MARKER_ENTRIES`
deep-link clause and `APP_PATHS` (including `/sessions/abc123`) are untouched — they assert the
shell, not the centre, and `GET /api/sessions/abc123` is step 009's concern.

- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 ✓ (both files), DoD-13 ✓, DoD-14 [manual/live, no test].
- `tests/app/CharacterScreen.test.tsx` was **not** touched — its two missing-prop errors are
  step 008's test-coder's.
- Tests were **not** run — the red gate is the verifier's. `npm run typecheck` could not be run
  either (no shell available in this session); see the hand-back.

### Step 007 — tests (2026-10-02)

One **new** test file, `frontend/tests/app/sessionsSectionState.test.ts` — a pure unit test, no
DOM, no router. 68 tests in 13 `describe` blocks; every `it` title ends `— DoD-N` of this step.
No source file was read: bindings come from `## Skeleton` → "Step 007 — frozen interface" (the
eleven observable fields with their initial values, the eight free-function signatures,
`workspace: SessionsState` as the second positional parameter of exactly the three mutating
effects) and "Step 004 — frozen interface" (`Session`, `SessionsState`). The three failure
sentences are asserted as **literals** taken from the step file / D18, never from the module's
unexported constants.

Conventions held: `globals: false` (every Vitest symbol imported explicitly); `fetch` stubbed
per test with `vi.stubGlobal`; **every request assertion keyed on the exact pathname plus query
string** (`seen()` returns `{method, path, search}`), never a prefix, because
`/api/characters/<id>/sessions` and `/api/characters/<id>/setups` share one; fixture ids are all
past `Number.MAX_SAFE_INTEGER` and the `last_used_at` order is **the reverse of the id order**
(`DAWN` id …001 newest, `DUSK` id …003 oldest), plus a `TIED_WITH_NOON` row with an equal
`last_used_at` and a *lower* id, so anything comparing or tie-breaking on `id` is caught. The
workspace `SessionsState` is a real instance built per test by `workspaceWith(rows)` and
asserted directly.

**`frontend/tests/app/sessionsSectionState.test.ts`** — covers DoD-1 … DoD-12:

- **DoD-1** (2) — a fresh `SessionsSectionState("c1")` snapshotted across all eleven fields
  equals the frozen initial values; a second clause pins "no setup, no sentinel" (R2).
- **DoD-2** (10) — `"loading"` while pending then `"ready"`; the request is **exactly**
  `GET /api/characters/c1/sessions` with `search: ""` by default and
  `?include_archived=true` **only** when `showArchived` is true; the server's rows in the
  server's order (including an order that is *not* the `last_used_at` order); empty listing
  ready; a failure and a transport failure both `"failed"`, rows kept, resolving undefined; two
  abort clauses (late response, and an `Error` named `"AbortError"`) assert the full eleven-field
  snapshot is byte-identical to the pre-abort snapshot.
- **DoD-3** (7) — the request is **exactly** `GET /api/characters/c1/setups` with
  `search: ""` — no `include_archived` at all, including while `showArchived` is true;
  `setupsStatus` `"loading"` → `"ready"` with the payload order; empty list ready; a failure
  keeps the previous setups **and** the selection and resolves; a failed choice load leaves the
  sessions list and `status` untouched (the separate-load rule); transport failure the same;
  abort writes nothing.
- **DoD-4** (5) — with `SETUP_ONE` selected: a reload still holding it keeps the selection (also
  when it moved position); a reload lacking it, and an empty reload, reset `selectedSetupId` to
  `null`; an already-null selection stays null.
- **DoD-5** (3) — `selectSetup(state, id)` then `selectSetup(state, null)`; no request issued and
  nothing else touched.
- **DoD-6** (8) — body is **exactly** `{ setup_id: null }` for "No setup" and
  `{ setup_id: "<id>" }` (a `string`) with a setup selected, both to
  `POST /api/characters/c1/sessions`, exactly one request and never the setups path; **never
  optimistic**: while pending `startStatus` is `"submitting"`, the new row is in **neither** the
  section nor the workspace state and `onStarted` has not been called; after the 201 the row is
  **first** in the section **and** in the workspace state, `startStatus` `"idle"`, `startError`
  null, `onStarted` called **exactly once** with the response's id **string**; the server's row
  (with the setup it answered with) is what renders; a start from an empty section + empty
  workspace works.
- **DoD-7** (5) — a 500, a 409 `setup_archived` and a transport failure each set `startError` to
  **"Could not start the session."**, leave **both** states' rows unchanged, never call
  `onStarted`, return `startStatus` to `"idle"` and resolve without throwing; two clauses record
  `state.startError` **inside** the next fetch stub to prove a later start cleared it **before**
  its request.
- **DoD-8** (15) — `applySectionSession`: absent working row inserted newest-first / between /
  last / into an empty list; an equal `last_used_at` inserts **after** the equal rows (never by
  id); a present row with unchanged `last_used_at` keeps its index with the new values (first
  row too, and with `showArchived` true); an archived row is removed while `showArchived` is
  false, is a no-op when absent (also on an empty list), is kept **in place** with the
  response's `archived_at` while it is true, is inserted by `last_used_at` when absent and the
  switch is on, and a restored row replaces its archived self in place.
- **DoD-9** (5) — `POST /api/sessions/<id>/archive`, once; `pendingId` is that id and the row is
  still in both states while pending; with `showArchived` **false** the row is gone from the
  section **and** the workspace state; with it **true** the row **stays in the section** carrying
  the response's `archived_at`; and a separate clause asserts it is **still gone from the
  workspace list** in that case (D5, working-only); `pendingId` ends `null`.
- **DoD-10** (5) — `POST /api/sessions/<id>/restore`, once; the section row ends with
  `archived_at` null; the workspace state holds it **at its `last_used_at` position**
  (`[DAWN, NOON, DUSK]` from `[DAWN, DUSK]`); `pendingId` held then cleared; a restore with the
  switch off still lands in both lists.
- **DoD-11** (6) — a failed archive sets **"Could not archive the session."** and a failed
  restore **"Could not restore the session."**, **neither** state changes, `pendingId` resets,
  nothing throws; a transport failure behaves identically; a failed row action leaves
  `startError` alone; two clauses record `state.error` inside the next fetch stub to prove a
  later row action cleared it **first**.
- **DoD-12** (5) — `setShowArchived` flips the flag and issues **no** request, and leaves rows,
  `status`, setups and selection alone; MobX `autorun` reading `sessions` re-runs after
  `applySectionSession` (insert, and archived-row removal), one reading `selectedSetupId`
  re-runs after `selectSetup`, one reading `showArchived` re-runs after `setShowArchived`.

- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 ✓. No `[manual/live]` item in this step.
- No other file was touched: `tests/app/CharacterScreen.test.tsx`'s two missing-prop errors
  remain step 008's test-coder's.
- Tests were **not** run — the red gate is the verifier's. `npm run typecheck` could not be run
  either (no shell available in this session); see the hand-back.

### Step 008 — tests (2026-10-02)

One **new** component test file plus the two amendments this step owns. Every `it` title ends
`— DoD-N` of **this** step for new clauses, and keeps its original 009 / 010 / 011-006 tag where
the clause is theirs. No source file was read: bindings come from `## Skeleton` →
"Step 008 — frozen interface" (`SessionsSectionProps` = `{ characterId: string; sessions:
SessionsState }`; the region's role / name / heading level; `CharacterScreenProps` and
`CharacterRouteProps` each gaining a **required** `sessions`), "Step 007 — frozen interface" and
"Step 004 — frozen interface" (`Session`, `SessionsState`). Every accessible name, sentence and
option label is the **literal** from the step file / `008.context.md` / `context.md` D1, D5, D18,
D19 — never a module constant (`NO_SETUP_VALUE` is deliberately unexported and is nowhere
asserted).

Conventions held: `globals: false` (every Vitest symbol imported explicitly); `fetch` stubbed per
test with `vi.stubGlobal`, **routed by the exact pathname plus query string** (`/api/sessions`,
`/api/characters/<id>/sessions` and `/api/characters/<id>/setups` share prefixes); section
assertions scoped through `within(getByRole("region", { name: "Sessions" }))`; the `Select`'s
options and the row `Menu`'s items read off `screen` because Mantine portals them; a row located
by its link's `href` and its trigger queried **within that table row** (`008.context.md` "Row
labels and the menu trigger"); start-time labels asserted **only** by the shape
`/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/`, never by an exact local value and never by calling
`formatSessionStart`; fixture ids past `Number.MAX_SAFE_INTEGER`; "no notification" checked as
`.mantine-Notification-root` being absent.

**`frontend/tests/app/SessionsSection.test.tsx`** (**new**) — covers DoD-1 … DoD-11:

- **DoD-1** (4) — the mount issues **exactly** `GET /api/characters/<C>/sessions` and
  `GET /api/characters/<C>/setups` and nothing else; the "Sessions" region with its "Sessions"
  heading, an **off** "Show archived sessions" switch, the "Setup" field showing **"No setup"**
  and an **enabled** "Start session"; one row per session **in the payload's order**, each
  linking to `/sessions/<id>` with a label of the fixed shape; the first row shows its
  `setup_name` and the second row's text is its label and nothing else (US-088.AC-2).
- **DoD-2** (1) — an empty listing shows "No sessions yet." and **no** table.
- **DoD-3** (2) — a failed listing shows "Could not load sessions" + "Retry" in the region, no
  table, **no notification**; "Retry" issues a second listing and the rows render.
- **DoD-4** (1) — "Start session" POSTs `{"setup_id": null}` once, the location becomes
  `/sessions/<the response's id>` (id past 2^53, so a coercion would show) and the passed
  `SessionsState` holds the new row.
- **DoD-5** (2) — with an **empty** setups listing and, separately, with a **failed** one,
  "Start session" is **enabled** and POSTs `{"setup_id": null}`; the failed case also shows
  "Could not load setups to choose from." in the region (US-024.AC-3, R2).
- **DoD-6** (2) — opening the Select lists **"No setup" first**, then the setups in the payload's
  order (an order that is not the fixtures' `created_at` order); **every** setups request carries
  `search: ""` (no `include_archived`); choosing a setup then starting POSTs
  `{"setup_id": "<its id>"}`.
- **DoD-7** (1) — D19: the mount load and the **first** opening see one setup, every later
  request also sees a second; the second opening issues a further setups request and offers the
  new setup (the option list is asserted on both openings).
- **DoD-8** (1) — a failed start shows "Could not start the session." in the region, the location
  is unchanged, no notification.
- **DoD-9** (1) — "Archive" from a working row's "Actions for …" menu POSTs
  `/api/sessions/<id>/archive` once and the row is gone (the sibling row stays); **no `dialog`
  and no `alertdialog` appears** (no confirm); turning the switch on issues the listing with
  `?include_archived=true` (the search sequence is `["", "?include_archived=true"]`), the row
  returns with an "Archived" badge and its menu offers **"Restore" and not "Archive"**.
- **DoD-10** (1) — "Restore" POSTs `…/restore`, the badge is gone, and turning the switch off
  issues a third listing with `search: ""` after which the row is still listed.
- **DoD-11** (1) — a failed archive shows "Could not archive the session." in the region, the row
  is still listed, no notification.

**`frontend/tests/app/CharacterScreen.test.tsx`** (**amended**) — adds DoD-12, DoD-13, DoD-14:

- **DoD-12** (4) — once the character has loaded the "Sessions" region is present with its own
  heading and, in **document order**, follows the "Persona" editor **and** the "Setups" region;
  `/characters/new`, "Character not found" and "Could not load the character" each render
  **neither** a Sessions region **nor** a "Sessions" heading.
- **DoD-13** (1) — an **archived** character still renders the region, and "Start session" there
  POSTs `/api/characters/<id>/sessions` with `{"setup_id": null}` and lands on the returned id.
- **DoD-14** (1) — navigating in-entry from `/characters/<a>` to `/characters/<b>` requests `b`'s
  sessions listing **once** with `search: ""`, shows only `b`'s row href, none of `a`'s, and the
  switch is back **off**.

Amendments to existing clauses in that file (DoD-16; **nothing dropped**):

- `renderScreen` now creates one `SessionsState` and passes it as `sessions` to **both**
  `CharacterScreen` (`/characters/new`) and `CharacterRoute` — this is what clears the two
  typecheck errors `(307,25)` and `(309,53)` the 008 skeleton recorded.
- One new helper, `sectionListing(request, characterId)`, answers `GET …/setups` **and**
  `GET …/sessions` empty for a loaded character, **any number of times** (so the Select's second
  setups request is tolerated), routed by exact path. It replaced the inline `setupsPath` branch
  in the eight existing-mode stubs whose load succeeds (009 DoD-3 ×2, DoD-5, DoD-6, DoD-7,
  DoD-10's Retry, DoD-11's failed Save, 010 DoD-11) and inside `serveCharacters` (which serves
  009 DoD-8 and DoD-12). 010 DoD-12's stub keeps its two **non-empty** setups branches and gained
  two explicit `…/sessions` branches.
- **009 `007` DoD-5's `expect(heading(/^sessions$/i))`** — kept **verbatim**; the region's own
  `Title order={3}` "Sessions" heading takes the old bare heading's place. Its document-wide
  `expect(loaders()).toEqual([])` is also unchanged (the section settles on an empty listing).
- **009 `007` DoD-1's `expect(queryHeading(/^sessions$/i)).toBeNull()`** in new mode — kept
  **verbatim**; new mode mounts no section.
- **010 `006` DoD-10's `precedes(section, heading(/^sessions$/i))`** — kept **verbatim**.
- **010 `006` DoD-12** — the one clause reshaped. `expect(listings).toHaveLength(1)` counted
  `GET /api/characters/<b>/setups`, which **both** sections now request. Kept in the form
  "`listings.length` is `> 0` and **every** such request carries `search: ""`", with a comment
  naming why; the old `listings[0].search === ""` is subsumed by the loop. Nothing else in that
  clause changed (B's setup row shown, A's absent, the Setups switch back off).

**`frontend/tests/app/App.test.tsx`** (**amended**) — adds DoD-15:

- **DoD-15** (2) — pressing "Start session" at `/characters/<id>` lands on `/sessions/<new id>`;
  the **tree** holds that row, it carries `aria-current="page"`, and it is the only row in the
  nested "Sessions of <name>" list under that character; **no `GET /api/sessions` after the
  POST** (`sessionsListRequests(calls.slice(postIndex + 1))` is `[]`, total still 1), keyed on
  that **exact** path. The second clause archives a session from the section's row menu: the
  archive POSTs once and the row is **gone from the tree**, again with no second workspace
  listing.
- `stubWorkspace` grew the rest of the sessions wire over a mutable row set: the character
  listing (honouring `?include_archived=true`), `POST …/sessions` (201 a row whose id is past
  2^53) and `POST /api/sessions/<id>/archive|restore`, all matched on the **exact** pathname. Its
  `GET /api/sessions` branch now answers the **working** rows of that same set (the tree never
  asks for archived ones); with the existing fixtures that is byte-identical to before.
- The inline `/characters/1` stub gained a `GET /api/characters/1/sessions` branch; its
  `setupsPath` branch already answers any number of requests, which covers the Select's second
  one. The `/characters/new` stub, which rejects every other URL, is **unchanged** (new mode
  mounts no section).
- **009 `008` DoD-8** ("no list request after the create", keyed on the exact `/api/characters`)
  and **011 `006` DoD-11** (one characters listing, one sessions listing at `/`) are unchanged
  and keep passing; `listRequests` is untouched. **`EMPTY_CENTRE_ROUTES` was not touched** — its
  `/sessions/1` entry is step 009's edit.

- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓ (the amendments above),
  DoD-17 [manual/live, no test].
- No other file was touched. Step 006's `tests/app/CharacterTree.test.tsx` and
  `tests/app/WorkspaceShell.test.tsx` already pass `sessions` / `storage` (its own tests record),
  so with this step's two prop additions **no known missing-prop error is left anywhere**.
- Tests were **not** run — the red gate is the verifier's. `npm run typecheck` could not be run
  either (**no shell is available in this session**); see the hand-back.

### Step 009 — tests (2026-10-02)

Two **new** frontend test files plus the two amendments this step owns. Every new `it` title ends
`— DoD-N` of **this** step; every clause that belongs to 008 / 009 / 010 / 011-006 / 011-008 keeps
its original tag. No source file was read: bindings come from `## Skeleton` →
"Step 009 — frozen interface" (`SessionScreenState(sessionId)` with `sessionId` / `session = null`
/ `status = "idle"`; `SessionScreenStatus`; `loadSessionScreen(state, signal?)` returning
`Promise<void>`; `SessionScreenProps = { sessionId: string; characters: CharactersState }`;
`SessionRouteProps = { characters: CharactersState }`; `SessionRoute` keying `SessionScreen` by the
id) and "Step 004 — frozen interface" (`Session`). Every text asserted is the **literal** from the
step file's Interface intent / DoD and `context.md` D5 / D17 / D18 — "Session not found", "Could
not load the session", "Retry", "No entries yet.", the badge "Archived", the fallback
"Character"; the module-private `SESSION_NOT_FOUND` constant is nowhere asserted.

Conventions held: `globals: false` (every Vitest symbol imported explicitly); `fetch` stubbed per
test with `vi.stubGlobal`, routed by the **exact** pathname (`/api/sessions/<id>`,
`/api/sessions`, `/api/characters`, `/api/characters/<id>/sessions` share prefixes);
session-screen assertions scoped to the **main region** (`getByRole("main")`), with the two
absence checks that could portal (`Actions for …`, any menu item) done document-wide;
start-time labels asserted **only** by the shape `/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/`, never by an
exact local value and never by calling `formatSessionStart`; fixture ids past
`Number.MAX_SAFE_INTEGER`; "no notification" checked as `.mantine-Notification-root` being absent;
a Mantine `Loader` as `.mantine-Loader-root`.

**`frontend/tests/app/sessionScreenState.test.ts`** (**new**) — covers DoD-1 (9 tests):

- a fresh `SessionScreenState("s1")` is `{ sessionId: "s1", session: null, status: "idle" }`, and
  an id past 2^53 is kept as the string it was given;
- `"loading"` while the request is pending, then `"ready"` with the returned row; the request list
  is **exactly** `[{ GET, "/api/sessions/s1", search: "" }]`; the loaded row's `id`,
  `character_id` and `setup_id` are the payload's own strings; a re-run from `"failed"` shows
  `"loading"` again;
- a 404 `session_not_found` → `"not-found"` with `session` still null; a 500 envelope and a
  transport failure (`it.each`) → `"failed"`; **every** load asserted with
  `resolves.toBeUndefined()`, so none rejects;
- an abort mid-flight leaves the whole field snapshot identical to the moment of the abort.

**`frontend/tests/app/SessionScreen.test.tsx`** (**new**) — covers DoD-2 … DoD-10:

- **DoD-2** (1) — a `Loader` while the GET is pending, then the screen (no loader left).
- **DoD-3** (1) — with the workspace `CharactersState` holding "Aria": a main-region link "Aria"
  with `href` `/characters/<character_id>`, a heading matching the start-time label's fixed shape,
  "No entries yet.", and exactly one session read.
- **DoD-4** (2) — `setup_name` "Tavern" is shown; with `setup_id` / `setup_name` null the setup
  text is absent and the main region's text, less the character's name, a label of the fixed shape
  and "No entries yet.", is **empty** (US-088.AC-2).
- **DoD-5** (1) — against an **empty** `CharactersState` (and binding `SessionScreen`'s own two
  props directly) the link reads "Character", keeps `href` `/characters/<character_id>`, and the
  request list contains **no** `/api/characters…` request at all.
- **DoD-6** (1) — an archived session shows the "Archived" badge in the main region and there is
  no "Archive", no "Restore", no "Actions for …" button and no menu item anywhere in the document.
- **DoD-7** (1) — a 404 `session_not_found` renders "Session not found" with **no** "Retry"
  button, no notification, and neither the failure sentence nor "No entries yet.".
- **DoD-8** (3) — a 500 envelope and a transport failure (`it.each`) each render "Could not load
  the session" + "Retry" with no notification; pressing "Retry" issues a **second** read of the
  same path and the ready header renders.
- **DoD-9** (1) — navigating in-entry from `/sessions/<a>` to `/sessions/<b>` (a probe beside the
  route, outside `<main>`) reads **b** once and shows only b's character link and setup label;
  a's are both absent — the proof that `SessionRoute` keys by id.
- **DoD-10** (1) — the ready main region holds **no** textbox and **no** button, and no
  notification.

**`frontend/tests/app/App.test.tsx`** (**amended**) — adds DoD-11:

- **`EMPTY_CENTRE_ROUTES` edit** — the array literal **lost its `/sessions/1` entry** and is now
  `["/", "/settings", "/search"]` (harvest E17, `009.context.md`). Both `it.each` clauses over it
  ("renders the shell at %s — DoD-10", "renders no centre content at %s — DoD-10") keep their 008
  tags and their assertions verbatim for the three remaining paths; the `*` "Page not found"
  clause and every 009 / 010 / 011-006 / 011-008 clause in the file are untouched.
- **DoD-11** (2) — at `/sessions/1`, with `GET /api/sessions/1` answered, the **main region**
  holds that session's screen: the character link with `href` `/characters/<id>`, a heading of the
  label's fixed shape, "No entries yet.", and neither "Session not found" nor "Page not found";
  exactly one read of `/api/sessions/1`. Then: from `/` (centre empty) a click on the **tree's**
  session row moves the location to `/sessions/<that id>`, reads that session once and renders its
  screen in the main region (UC-024, UC-069).
- `stubWorkspace` gained **one** branch — `GET /api/sessions/<id>` answered from the rows it
  holds, archived or not, and 404 `session_not_found` for an unknown id — matched on the **exact**
  pathname, beside the `/api/sessions` listing and the `…/archive|restore` actions it already
  served. Step 006's and step 008's widenings are **built on, not undone**; `listRequests` and
  `sessionsListRequests` are untouched, so 009 `008` DoD-8 and 011 `008` DoD-15 keep their meaning
  (DoD-15's post-start screen now also loads its session; that clause asserts the location and the
  tree).

**`frontend/tests/entries.test.tsx`** (**amended** — stub widening only) — adds DoD-12:

- `stubAppIdentity` gained one branch for the **exact** path `/api/sessions/abc123`, answered with
  the backend's 404 `session_not_found` envelope (any status is allowed: the clauses mounting the
  `app` entry at `/sessions/abc123` assert the shell and the nav, never the centre). Step 006's
  `GET /api/sessions` branch is kept.
- **No assertion about any boot outcome changed**: the "a deep link too — DoD-1" clause and the
  `APP_PATHS` "renders the shell at %s too — DoD-11" block are byte-unchanged, as is step 006's
  own `— DoD-12` clause.
- **DoD-12** (1) — mounting the `app` entry at `/sessions/abc123` still renders the shell nav and
  the "User menu" button, and the recorded request list contains `/api/sessions/abc123` (the stub
  rejects any path it does not know, so this is the proof the widening is what is exercised).

- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 [manual/live, no test].
- No other file was touched — `AppBoot.test.tsx` renders `App` at `/` and is unaffected
  (`009.context.md`).
- Tests were **not** run — the red gate is the verifier's. `npm run typecheck` could not be run
  either (**no shell is available in this session**); see the hand-back.

## Notes & Issues

_populated by the coder when worth saying_

## Ultra phase

- orient: done 2026-10-02
- harvest: done — docs/.cache/ultra/011.rp-sessions/harvest.md (2 reports)
- skeleton: done — steps 001, 002, 003, 004, 005, 006, 007, 008, 009
- tests: done — steps 001, 002, 003, 004, 005, 006, 007, 008, 009
- red-gate: PASS (run 2) — run 1 FAIL: 001 TEST (helper name collision shadowing feature 004's `auth_sessions` helpers), fixed by rename
- code: done — steps 001, 002, 003, 004, 005, 006, 007, 008, 009 (no re-freeze, no escape valve)
- verify: PASS (run 1) — 4659 tests, 0 failures (backend 2093, frontend 2566); 5 `[manual/live]` outstanding
