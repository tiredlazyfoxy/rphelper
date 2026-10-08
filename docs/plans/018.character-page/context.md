# Feature 018 — Character page · feature-wide context

## What this feature is

This feature turns `/characters/:id` into the one place where everything about a
character lives, and makes it the natural place to begin a roleplay. The body holds the
name and persona, the character's notes as a **grid of the wall's own cards** (reorderable
in place), its setups, its **configuration** (model, system prompt, three tool switches,
editable in place), its sessions, and at the end a **composer**. Writing in that composer
and pressing Send creates a session under the character, with the message as the opening
row of its current zone, in one request and one transaction. The client then navigates
into the workspace on that session. `/characters/new` becomes a **draft page**: nothing is
persisted until the roleplayer commits a non-blank name. From then on name and persona
save on focus loss.

The agreed boundary is `brief.md` in this folder. Its Definition and Scope In/Out bound
every step and are **not** widened. The brief's one open question (kind switch or setup
choice on this composer) is closed by product, not by choice: **D1**.

## Product ids

`FEAT-020` via **UC-073**, **UC-074**, **US-096**, **US-097**; `FEAT-008` via **UC-080**,
**US-117**. Exercised from the UI (backend halves are 017's): **UC-048**, **US-059**,
**US-061.AC-3**, **US-106**, **US-139**. **UC-017** (create a character) is reached through
the draft page.

| Criterion | Where it lands |
|---|---|
| US-096.AC-1 (persona, notes, setups, configuration, sessions on one page) | `005` (notes grid), `007` (configuration section), `009` (assembly and order) |
| UC-073 (work on any of these without navigating away) | `005`, `007`, `009` |
| US-097.AC-1 (draft page with nothing entered → nothing persisted) | `008` (no create without a non-blank name), `009` (draft marker; no request) |
| US-097.AC-2 (something real entered → the character exists and is listed) | `008` (create + apply to the workspace list), `009` (the tree shows it; URL replaced) |
| UC-074 (persist on the first real input; leaving with nothing entered persists nothing) | `008`, `009` |
| US-117.AC-1 (writing in the page composer creates a session with a turn being drafted) | `001`, `002` (one route, one transaction), `004` (page composer), `009` (mounted) |
| US-117.AC-2 (the written message is the opening message of that turn's discussion) | `002` (a current-zone row), `004` |
| US-117.AC-4 (no kind switch, no setup choice on this composer) | `004` (the page composer renders the core alone), `009` |
| UC-080 (steps 1–4; the postcondition's "no switch, no setup") | `002`, `004`, `009` |
| UC-048 / US-059.AC-2 / US-062.AC-1 (character-level overrides set from the page) | `006` (API + state), `007` (section) — the resolution itself is 017's |
| US-106.AC-1 (no character model → first enabled model) | `007` states it on the page; the capture is 017's |
| US-139.AC-1 (a character model change does not reach existing sessions) | `007` states it on the page; the backend guarantee is 017's |
| US-061.AC-3 (no language override on the character) | `006`, `007` (no language field, no language key) |

**Not delivered here. Recorded as forward notes, never faked with stand-in tests:**

- **US-117.AC-3 / UC-080 step 5** (the assistant answers the opening message) — `021`,
  which composes on the session once it exists. The create-and-seed route stays JSON and
  makes no model call (**D2**). No DoD item covers AC-3.
- **US-107 on the page composer** (refuse a send when no model is enabled) — the page
  composer makes no model call in 018, so it has nothing to refuse. `021` decides whether
  the page composer takes the core's `sendBlockedReason` when it adds the reply
  (`outcome.md`).

## Build prerequisites — what is source, and what is declared by plan

001..011 are built and committed. 012 is in the working tree (uncommitted). **013, 014,
015, 016 and 017 are planned, not built**. 018 is built after all of them, so it binds to
two kinds of fact, marked throughout this folder:

- **(A) source** — harvested from code that exists today.
- **(B) declared** — a name or behaviour that exists only in an upstream plan's prose.
  **The skeleton agent must re-verify every (B) fact against the built code at build time**
  and record any drift in `status.md`'s `## Skeleton` before freezing a signature.

| Upstream artifact | Kind | What 018 relies on | Needed by |
|---|---|---|---|
| `backend/app/routers/sessions.py` `start_own_session` (`POST /api/characters/{character_id}/sessions`, 201, `StartSessionRequest \| None` body, `SessionResponse`) | A | the route 018 extends (011 D2) | `002` |
| `backend/app/services/sessions.py` `start_session`, `RpSession`, `_require_parent_character`, `_require_choosable_setup`, `_now_text` | A | the creation transaction 018 extends | `002` |
| `backend/app/models/sessions.py` `StartSessionRequest`, `SessionResponse` | A | the request and response 018 widens | `001` |
| 012 `backend/app/services/messages.py` `append_message`, `StreamMessage`, `_bump_session`; `backend/app/models/stream.py` `MessageResponse`, `NonBlankText` | A (working tree) | the insert 018 extracts; the opening message's wire shape and validation | `001`, `002` |
| 017 `002`: `start_session` captures the model inside its transaction | B | the capture the opening-message path shares | `002` |
| 017 `005`: `GET` / `PATCH /api/characters/{character_id}/configuration` (`CharacterConfiguration`) | B | the configuration block's routes | `006` |
| 017 `006`: `frontend/src/app/configurationApi.ts` (`ModelRef`, `EnabledModel`, `fetchEnabledModels`, …) and its DoD-6 guard test | B | types reused; module extended; guard amended | `006` |
| 013 `006` + 014 `003` + 017 `011`: `frontend/src/app/Composer.tsx` (`state`, `signal?`, `sendBlockedReason?`) and its tests | B | the composer split into a core | `003` |
| 013 `001`: `frontend/src/app/streamApi.ts` `Message` | B | the opening message's frontend type | `004` |
| 014 `003`: `app/pasteCost.ts` `isEnormousPaste`, `shared/notifyWarning.ts` | B | the paste warning moved into the core | `003` |
| 015 `006`/`007`/`009` + 016 `002`/`003`/`004`: `MemoLevelState`, `loadMemoLevel`, `MemoLevelGroup` (`state`, `title`, `headingOrder`, `onRetry`, `reorderable?`), `MemoChainSection`'s `DndContext`, `app/memoReorder.ts` (drop decision + drop effect over `MemoLevelState[]`), `CharacterNotesSection` | B | the notes grid | `005` |
| 011 `004`: `frontend/src/app/sessionsApi.ts` `Session`, `startSession`; `sessionsState.ts` `SessionsState`, `applySession` | A | the start call, the workspace sessions store | `004` |
| 009 `006`/`007` + 010 + 011 `008` + 015 `009`: `characterScreenState.ts`, `CharacterScreen.tsx` (`CharacterScreenProps = { characters, characterId }`, `CharacterRoute` keyed by id), `SetupsSection`, `SessionsSection` | A (+ B for 015's mount) | the page 018 rebuilds | `008`, `009` |
| `frontend/src/app/App.tsx` routes `/characters/new` and `/characters/:id` inside `WorkspaceShell` | A | unchanged; read only | `009` |

`App.tsx` passes `CharacterScreen` only `characters` and `characterId` today. The page
composer needs the workspace `SessionsState` (011 `008` already threads it to
`SessionsSection`, A). `009` reuses whatever prop carries it. If the built screen does not
receive it, the skeleton reports that before freezing.

## Wire contract — what 018 changes

**`POST /api/characters/{character_id}/sessions`** (011's route, `routers/sessions.py`):

| Body | Answers |
|---|---|
| omitted, `{}`, `{ setup_id }`, `{ opening_message }`, or both keys | **201** `StartedSession` |

```
StartedSession { …the eight Session keys, unchanged…,
                 opening_message: Message | null }   // null exactly when none was sent
```

`Message` is 012's eight-key wire shape (`id`, `session_id`, `role`, `kind`, `text`,
`settled_at`, `created_at`, `updated_at`). The opening message is a **current-zone row**:
`role` `"user"`, `kind` null, `settled_at` null, `session_id` the new session's id, `text`
verbatim.

Request rules: `opening_message` is optional. An absent or `null` value means "no opening
message", which is exactly 011's behaviour. A present value must be non-blank (012's
`NonBlankText`): whitespace-only → **422**, and nothing is created. It is stored verbatim.
`setup_id` keeps 011's rules. Unknown keys are ignored.

Failures are 011's, unchanged: `character_not_found` 404 (missing or another user's
character), `setup_not_found` 404, `setup_archived` 409, 422, 401. **A refusal creates
nothing**: no session row and no message row.

No other route changes. 017's character configuration routes are consumed, not changed
(017 `context.md` "Wire contract").

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

- `docs/architecture/workspace-shell.md`: **"The character page"** (two columns, same
  components in a different arrangement, the draft page, "The composer, and how a session
  starts here", its `_TBD:` closed by D1); the geometry table (composer 720px / 18px, min
  42px, no max, no handle); "The wall's contents" and "`@dnd-kit` is finally used"
  (keyboard sensor required, a note being edited is not draggable).
- `docs/architecture/backend-structure.md`: the stream route table's
  `POST /api/characters/{character_id}/sessions` row and its two bullets ("Starting a
  session by writing is one route and one transaction"; "It is character-addressed, and
  it creates nothing settled", with the first-reply `_TBD:` closed by D2); "Routers versus
  services"; "The JSON id boundary"; "The error model".
- `docs/architecture/frontend-structure.md`: "Routing inside the `app` entry" (`/characters/:id`
  starts sessions with one post; `/characters/new`; the archive-toggle `_TBD:`, D11);
  "State — MobX 6"; "Ids are strings"; "The API client".
- `docs/architecture/ui-conventions.md`: the composer conventions (auto-growing text area
  with no handle, labelled Send); "Create and edit are always a `Modal`" and its draft-page
  exception; "Async feedback" (`notifyFailure` for a failure with no place of its own; no
  success notification); "Mutations are never optimistic".
- `docs/architecture/domain-rules.md`: **R2** (no setup is first-class), **R4** (the model
  is captured at creation), **R5** (owner scope in SQL), **R6** (archive is not a lock),
  **R10** (nothing typed is lost), **R11** (settle is the only door into the record; the
  opening message is a zone row, not an exception).
- Product: `use-cases/FEAT-020.workspace-shell.md`, `stories/FEAT-020.workspace-shell.md`,
  `use-cases/FEAT-008.rp-sessions.md`, `stories/FEAT-008.rp-sessions.md`,
  `stories/FEAT-013.session-configuration.md`.

Cited, never copied.

## Files this feature touches

```
backend/
  app/services/messages.py         # + transaction-neutral zone insert; append uses it  (001)
  app/models/sessions.py           # + opening_message request field; StartedSession response (001)
  app/services/sessions.py         # + create-and-seed in start's one transaction        (002)
  app/routers/sessions.py          # route answers StartedSession; docstring             (002)
  tests/test_zone_message_insert.py (new), tests/test_sessions_models.py                 (001)
  tests/test_sessions_service.py, tests/test_sessions_router.py                          (002)
frontend/
  src/app/ComposerCore.tsx         # NEW — the shared presentational composer             (003)
  src/app/Composer.tsx             # the stream's composer, rebuilt on the core           (003)
  src/app/sessionsApi.ts           # + startSessionWithMessage; startSession keeps 8 keys (004)
  src/app/characterComposerState.ts  # NEW — page composer data class + send effect       (004)
  src/app/CharacterComposer.tsx    # NEW — the page composer                              (004)
  src/app/memoDnd.ts               # NEW — shared sensors + announcements                 (005)
  src/app/MemoChainSection.tsx     # uses memoDnd                                         (005)
  src/app/MemoLevelGroup.tsx       # + opt-in grid layout                                 (005)
  src/app/CharacterNotesSection.tsx  # grid + reorderable + its own DndContext            (005)
  src/app/configurationApi.ts      # + character configuration types and two calls       (006)
  src/app/characterConfigState.ts  # NEW — configuration block state                      (006)
  src/app/CharacterConfigSection.tsx # NEW — the configuration block                      (007)
  src/app/characterScreenState.ts  # draft page + blur-save                               (008)
  src/app/CharacterScreen.tsx      # draft page, body order, mounts                       (009)
  tests/app/ComposerCore.test.tsx (new), tests/app/Composer.test.tsx,
  tests/app/ComposerPasteWarning.test.tsx                                                 (003)
  tests/app/sessionsApi.test.ts, tests/app/characterComposerState.test.ts (new),
  tests/app/CharacterComposer.test.tsx (new)                                              (004)
  tests/app/memoDnd.test.ts (new), tests/app/MemoLevelGroup.test.tsx,
  tests/app/MemoChainSection.test.tsx, tests/app/CharacterNotesSection.test.tsx           (005)
  tests/app/configurationApi.test.ts, tests/app/characterConfigState.test.ts (new)        (006)
  tests/app/CharacterConfigSection.test.tsx (new)                                         (007)
  tests/app/characterScreenState.test.ts                                                  (008)
  tests/app/CharacterScreen.test.tsx, tests/app/App.test.tsx, tests/entries.test.tsx      (009)
```

**Not touched. A step that touches one is out of scope:**

- Backend: `db/schema.py` (no column, no table), `errors.py` (no new code),
  `models/stream.py` (imported, not edited), `routers/stream.py`, every 009 / 010 / 015 /
  016 / 017 module, `main.py` (no new router), `dependencies.py`, `ids.py`,
  `tests/conftest.py` (no shared fixtures). No new Python dependency.
- Frontend: `App.tsx`, `WorkspaceShell.tsx`, `CharacterTree.tsx`, `SessionsSection.tsx`,
  `sessionsSectionState.ts`, `SetupsSection.tsx`, `SessionScreen.tsx`, `SessionStream.tsx`,
  `streamState.ts`, `streamApi.ts`, `KindSwitch.tsx`, `memoLevelState.ts`,
  `memoReorder.ts`, `memoChainState.ts`, `memosApi.ts`, every 017 module other than
  `configurationApi.ts`, `charactersApi.ts`, `charactersState.ts`, `src/shared/*`,
  `src/admin/*`, **`src/shell.css`, `src/global.css`** (no stylesheet, no selector, no
  `.css` file), `vite.config.ts`, `package.json` and the lockfile (**no new npm
  dependency**: `@dnd-kit` arrives with 016), `tests/setup.ts`, `tests/conventions.test.ts`,
  `tests/stylesheets.test.ts`, `tests/ids-are-strings.test.ts`.

## Cross-cutting constraints every step holds

**One transaction for create-and-seed (US-117.AC-1).** The session insert and the opening
message insert commit together or not at all. No nested `begin()`. No client sequence of
"create, then post".

**Nothing settled is created (R11).** The opening message is a current-zone row. It is
never written with a `kind` or a `settled_at`.

**Owner scope lives in SQL (R5).** The opening message carries the caller's id wherever
012's append writes it. The parent-character check is 011's, unchanged.

**No second composer, no second note card (brief Out).** The page composer renders the
shared composer core (D4). The notes grid renders `MemoLevelGroup`'s own cards (D8).

**Pure data contracts.** Data classes hold observable fields only (`makeAutoObservable`).
Derivations and effects are free functions taking the state first. Effects `runInAction`
after `await`, check `signal?.aborted` before writing, never reject, and write fixed
sentences rather than backend prose. One instance per mount via `useState(() => …)`,
passed as a prop, no React context, `observer` on every reader. Loads are aborted on
unmount. Mutations take no signal, so a started save still reaches the server (015 D5).

**Never optimistic.** What renders is the server's answer: a returned row, a returned
configuration, or a re-read. The one sanctioned exception is 016 D7's reorder, which the
grid inherits unchanged.

**Nothing typed is lost (R10).** A failed send keeps the composer draft. A failed save
keeps the typed name or persona. Leaving the page saves pending edits (D7).

**Ids are strings.** Session, message, character, memo and server ids are `string`,
compared by equality, never parsed, never used to sort. The new session id is used exactly
as received for navigation.

**Styling is Mantine only.** Component props, style props and inline `style`. No `.css`
file and no new selector. The page is two columns **by construction**: the shell grid is
already tree + main (016 D1), and the wall lives only in `SessionScreen`.

**Every icon-only control goes through `shared/IconButton`.** Tests find controls by
accessible name. The UI strings table is the contract.

**TypeScript only.** No `.js` / `.jsx` / `.mjs` / `.cjs`.

## UI strings — the contract tests bind to

Exact text. Components render these and nothing else for these purposes. Strings owned by
upstream plans keep their owners' tables (009's character screen, 011's Sessions section,
013's composer, 015 / 016's notes, 017's model strings) and are not repeated here.

| Where | String | Role / element |
|---|---|---|
| Draft page | heading **"New character"** (009's, kept); a `Badge` **"Draft"** beside it; dimmed text **"Nothing is saved until you enter a name."** | `009` |
| Name field, blank on an existing character | **"A character needs a name."** | the Name input's error (`008` produces, `009` renders) |
| Character create / save failure | **"Could not create the character."** / **"Could not save the character."** (009's sentences, kept) | inline `Alert` (`008`, `009`) |
| Page composer | region **"Start a session"** with heading **"Start a session"**; inside it the core's textbox **"Composer"** and button **"Send"** | `004` |
| Configuration block | region **"Configuration"** with heading **"Configuration"** | `007` |
| Model control | `Select` **"Model"**; first option **"First enabled model"** (the unset value); then **"<model_name> (<server_name>)"** per enabled model; a configured model that is not enabled shows as a disabled option **"<model_name> (not enabled)"**; description **"Applies to sessions started from now on. Existing sessions keep their model."** | `007` |
| System prompt control | `Textarea` **"Character system prompt"** | `007` |
| Tool controls | `SegmentedControl`s **"Memo search"**, **"Session search"**, **"Web search"**, each with options **"Default"** / **"On"** / **"Off"** | `007` |
| Resolved-value lines (one under each control) | model: **"Not set: new sessions take the first enabled model."** / **"Set on this character."**; prompt: **"Not set: no system prompt."** / **"Set on this character."**; each tool: **"On (default)"** / **"On (set on this character)"** / **"Off (set on this character)"** | text (`006` produces, `007` renders) |
| Configuration load failure | **"Could not load the configuration"** + button **"Retry"** | in the region (`007`) |
| Configuration save failure | **"That model is no longer enabled."** (409 `model_not_enabled`, 017's sentence) / **"Could not save the configuration."** (anything else) | text in the region (`006` writes, `007` renders) |

No success notification exists anywhere. The page composer's send failure goes through
`notifyFailure` (D5) and is therefore not asserted as text. Every other 018 failure
renders in place.

## Decisions — settled, with their reasoning

"009 Dn", "011 Dn", "013 Dn", "015 Dn", "016 Dn", "017 Dn" refer to those folders'
`context.md`.

### D1 — The page composer offers neither the kind switch nor a setup choice (product; closes the brief's open question)

US-117.AC-4 states it, and UC-080's postcondition gives the reasons: the kind is already a
turn, and FEAT-007 forbids forcing a setup choice. The session is created with `setup_id`
NULL, which R2 makes the first-class case. `workspace-shell.md`'s `_TBD:` was written
before the gap-closure round added AC-4. `outcome.md` closes it citing US-117.AC-4. The
Sessions section's own "Start session" with its Setup select (011 D1) stays as built: it is
the place to start **with** a setup, and US-117.AC-4 only constrains this composer.

### D2 — No assistant reply in 018; the route stays JSON (user decision 2)

US-117.AC-3 is deferred to `021`, which composes on the session once it exists. The
create-and-seed route makes **no model call** and answers JSON, as `backend-structure.md`
designs it. `outcome.md` closes that doc's first-reply `_TBD:` and the matching
`quick-reference.md` open item with "owed by `021`". No DoD item stands in for AC-3.

### D3 — Same route, one optional field, one transaction, one insert (planner decision, orchestrator-prescribed)

- 011's `StartSessionRequest` gains an optional **`opening_message`** (`NonBlankText`).
  011's route answers a new **`StartedSession`** response: `SessionResponse`'s eight keys
  plus `opening_message` (a 012 `MessageResponse`, or null). 011's own calls are
  unaffected apart from the extra null key. That is why 011's exact-keys wire assertion is
  amended in `002`.
- The opening message is inserted **inside the same `with connection.begin():`** as the
  session, after the session insert and after 017's model capture. `last_used_at` stays
  the creation instant (011 D3). Creation and the first content write are one instant, and
  no second bump is needed.
- **One insert, not two.** `services/messages.py` gains a **transaction-neutral** public
  helper that only inserts a current-zone user row and returns it: no `begin()`, no
  session check, no bump. 012's `append_message` calls it inside its own transaction.
  `services/sessions.py` calls it inside the creation transaction.
- **A narrow service-import exception, taken deliberately** (017 D12 and 015 D11
  precedent): `services/sessions.py` imports **only** that helper and the message value
  type from `services/messages.py`. The rule's reason (a service operation owns its
  transaction, 010 D6) concerns operations that open a transaction. The helper opens none.
  A second copy of the insert would drift from 012's on the first column change.
- `start_session` keeps its 011 signature and return value, so 011's and 017's callers and
  tests are untouched. A sibling operation creates **and** seeds, and the two share one
  private transaction body.

### D4 — The composer is split into a shared core (user decision 3)

`app/ComposerCore.tsx` is presentational and owns what both hosts share: the auto-growing
`Textarea` labelled "Composer" (no handle, ~42px minimum, no maximum), the stream column
geometry (720px / 18px), the labelled **"Send"**, 014's enormous-paste warning, and
017's optional **`sendBlockedReason`** (Send disabled and the reason shown). It takes the
draft, a draft-change callback, a send callback, whether Send is enabled, an optional host
paste hook (run after the warning), and slots for content under the text area and for
controls beside Send. It knows nothing of sessions, kinds or routes.

The stream's `Composer` keeps its public props and behaviour (013 `006`, 014 `003`,
017 `011`). It renders the core and passes the stream-only pieces: the preview line,
"Settle", "Discard empty zone", partner-paste routing, and the reason **only on *my
turn***. The page composer renders the core alone. One component, two hosts. Reasoning:
`workspace-shell.md` forbids a second composer because two drift on the first change. The
core is the one place a change lands.

### D5 — The page composer: one post, then navigate (planner decision, orchestrator-prescribed)

`app/characterComposerState.ts` holds the page's own draft and in-flight flag. Send posts
**once** through `sessionsApi.ts`'s new start-with-message call. That call returns the
started session, and its eight session keys are applied to the workspace `SessionsState`
(`applySession`), so the tree shows the new session at once. The client then router-pushes
to `/sessions/<id>` with the id exactly as received. It is a push, not a replace, because
the character page stays a valid place to come Back to (011 D1). On failure the draft is
kept (R10) and the error goes to `notifyFailure`: the composer has no inline error place,
which matches 013 D15. Send is disabled while the draft is blank or a send is in flight. A
navigation that would fire after the page has unmounted is skipped. The returned opening
message is **not** used to pre-seed the stream, because the session screen re-reads its
zone on mount (013 D13).

`startSession` (011's call, used by the Sessions section) now receives the wider response.
It resolves to **exactly the eight `Session` keys**, so the workspace store never holds a
ninth key.

### D6 — The draft page: the first non-blank name, committed on focus loss, creates the character (user decision 4; trigger interpreted here)

- `/characters/new` renders a **draft**: the heading, a "Draft" badge, the marker line, the
  Name field and the Persona editor. Nothing else renders. Notes, setups, configuration,
  sessions and the composer each need an id. No Create button.
- **The create fires when the Name field loses focus holding non-blank text.** It posts the
  name **and** whatever persona the draft already holds. **Interpretation, flagged:** the
  user decision says "on the first non-blank name". A per-keystroke trigger would create a
  one-letter character and then remount the screen in the middle of typing, because
  `/characters/new` and `/characters/:id` are different route elements. The blur trigger is
  the earliest point at which the name is a name. A blank name blurring sends nothing, and
  persona alone persists nothing, because the name is required server-side (US-097.AC-1).
- **No double create:** while the create is in flight, both fields are read-only and a
  second commit sends nothing. Once created, the state holds the row, so the draft is over
  and any further commit is a no-op.
- On success the row is applied to the workspace `CharactersState` (the tree lists it,
  US-097.AC-2) and the client navigates **with `replace`** to `/characters/<id>` (009 D1's
  navigation, kept), unless the screen has already unmounted.
- On failure "Could not create the character." renders inline and the draft stays.

### D7 — Name and persona save on focus loss; Save and Create are gone (user decision 4)

Replaces 009 D2's explicit Save, as 009's forward note allowed:

- **Name**: on focus loss, unchanged → nothing. Blank → **no request**: the field keeps
  the typed text, shows "A character needs a name.", and the saved name stays the server's.
  Otherwise `PATCH {name}`.
- **Persona**: on focus leaving the editor area (not merely moving into its own toolbar),
  unchanged → nothing, otherwise `PATCH {sheet}`.
- Each save applies the returned row to the workspace state and replaces the held
  character **only if the returned `updated_at` is not older** than the held one's (015
  D5's rule, because a name save, a persona save and an archive can overlap). The draft
  field is replaced by the server's value only if it still equals what was sent. Text typed
  during the request is kept.
- A field whose save is in flight sends nothing on another blur. The next blur or the
  flush picks the edit up.
- **Leaving keeps the edit (R10).** On unmount, a changed non-blank name and a changed
  persona are saved by the same rules. On the draft page a non-blank uncommitted name
  creates the character, without navigating. Blur is not reliably fired when an element
  leaves the DOM (015 D5).
- **Archive / Restore** stay as 009 built them (labelled buttons, inline failure, the draft
  untouched).

### D8 — The notes grid: one opt-in layout on the same group, with its own drag context (planner decision, orchestrator-prescribed)

- `MemoLevelGroup` gains an optional **layout** prop. The default is the list, so the wall,
  `/settings` and every existing caller are unchanged. **Grid** arranges the same listitems
  as a responsive multi-column grid using Mantine props or inline style only. When it is
  also `reorderable`, the per-level `SortableContext` uses dnd-kit's **rect** sorting
  strategy instead of the vertical one. No second card component and no second group
  component.
- `CharacterNotesSection` passes grid **and** `reorderable` (016 D8's forward note). It
  wraps its group in **its own** `DndContext`, because the page has no chain section. Its
  drag-end calls 016's drop effect with its one level state, and the drop decision and
  effect are reused unchanged.
- The sensors (pointer at 6px distance, keyboard with `sortableKeyboardCoordinates`) and
  the position-only announcements are **factored out of `MemoChainSection`** into
  `app/memoDnd.ts` and used by both, rather than copied. That keeps the keyboard path
  (US-102, `ui-conventions.md` accessibility floor) identical in both places.

### D9 — The configuration block: the character's own values, editable in place (user decision 5)

- 017's `CharacterConfiguration` is **flat**: each of `model`, `system_prompt` and the
  three tools is the character's own value, or null for "not set". It is not 017's
  `Setting<T>` shape, which exists only for sessions. The briefing's "per 017's `Setting<T>`
  shapes" is therefore applied as the **meaning** of `Setting`: each control shows its
  resolved value and whether it is set here or comes from the default. A null model means
  "new sessions take the first enabled model" (US-106, 017 D1). A null prompt means none. A
  null tool means on (017 D5).
- Each control saves **only its own key** through `PATCH …/configuration` and renders the
  returned configuration (never optimistic). The model `Select` and the tool
  `SegmentedControl`s save on change. The system prompt saves on focus loss when changed,
  and a blank prompt is sent as null (017 D6). "First enabled model" sends `model: null`,
  which 017 D10 allows on the character route.
- A configured model that is not enabled is shown, not hidden, as a disabled
  "(not enabled)" option (017 D16's posture).
- **No language field and no language key** (US-061.AC-3, R1).
- Failures render inline in the region (017 D19's posture). A 409 `model_not_enabled`
  re-reads the enabled list. No notification.
- The model description states US-139.AC-1 so the roleplayer knows a change reaches new
  sessions only.

### D10 — Body order, two columns, no wall (planner decision, orchestrator-prescribed)

On an existing character, in document order: header (name heading, Archived badge) →
Name + Persona (+ Archive / Restore) → **Notes** → **Setups** → **Configuration** →
**Sessions** → **Start a session** (the composer). The notes move **ahead** of setups,
because they are the page's grid (`workspace-shell.md`), and the composer ends the body
("the body ends with a composer"). This amends 015 `009` DoD-4's "Notes follows Sessions".
The page is tree + body because the shell grid has two tracks and the wall exists only in
`SessionScreen` (016 D1). So **no `shell.css` change** is made. A test pins that the page
renders no note wall.

### D11 — The archive-toggle `_TBD:` is already answered by source (record only)

`frontend-structure.md`'s "where the archive toggle sits" `_TBD:` was answered piece by
piece as features were built: the tree header's "Show archived" (009 D4), the Setups
section's "Show archived setups" (010), and the Sessions section's "Show archived sessions"
(011 D5). 018 adds none and moves none. `outcome.md` asks the architect to record
section-local placement and close the `_TBD:`.

### D12 — Nine steps

Backend in two: the extracted insert with the request and response models, then the
create-and-seed service with the route. Frontend in seven: the composer core; the page
composer (API call, state and component, small enough together); the notes grid (shared
drag config, group layout and the section, together because each part alone is under
50 lines); the configuration API and state; the configuration section; the screen state;
the screen assembly, which is last because it mounts everything.

## Step map

| Step | Subject | Est. LoC | Depends on |
|------|---------|----------|------------|
| 001 | zone insert helper; `opening_message` request field; `StartedSession` response model | ~60 | 012 in source |
| 002 | create-and-seed service + route | ~90 | 001; 017 `002` delivered |
| 003 | `ComposerCore.tsx`; `Composer.tsx` rebuilt on it | ~120 | 013 `006`, 014 `003`, 017 `011` delivered |
| 004 | `startSessionWithMessage`; `characterComposerState.ts`; `CharacterComposer.tsx` | ~130 | 002 (wire; tests stub `fetch`), 003 |
| 005 | `memoDnd.ts`; `MemoChainSection` on it; `MemoLevelGroup` grid; `CharacterNotesSection` grid + reorder | ~130 | 016 `003`, `004`, 015 `009` delivered |
| 006 | character configuration calls; `characterConfigState.ts` | ~150 | 017 `005`, `006` delivered |
| 007 | `CharacterConfigSection.tsx` | ~130 | 006 |
| 008 | `characterScreenState.ts`: draft page + blur-save + flush | ~130 | none within 018 |
| 009 | `CharacterScreen.tsx`: draft page, body order, mounts | ~130 | 004, 005, 007, 008 |

`003`, `005`, `006` and `008` are independent of each other. `001` → `002` are ordered.

## Test conventions

Inherited from 011, 013, 015, 016 and 017 `context.md` "Test conventions":

- Backend: pytest from `backend/`, no shared fixtures, `conftest.py` untouched, schema from
  `schema.metadata.create_all` on a file-local engine, file-local seeding, two users for
  isolation.
- Frontend: Vitest with `globals: false`, `tests/` mirroring `src/`, `fetch` stubbed per
  file with `vi.stubGlobal`, `AppProviders` around rendered components, `MemoryRouter`
  where routed, the per-file `vi.mock` of `src/shared/MarkdownEditor` as a labelled
  `<textarea>`, and assertions on rendered behaviour only.

Additions for 018:

- **Test names.** Backend: `test_<behavior>__S018_<SSS>_DoD<n>`. Frontend: each `it` title
  ends **`— DoD-N`** of its own 018 step. An amended upstream test keeps its assertion
  and ends its title with the 018 `— DoD-N` that amends it. It may name the upstream item
  earlier in the title.
- **Stubs by exact path, query and method.** `/api/characters`, `/api/characters/<id>`,
  `/api/characters/<id>/sessions`, `/api/characters/<id>/setups`,
  `/api/characters/<id>/configuration`, `/api/memos?scope=character&scope_id=<id>`,
  `/api/memos/order` and `/api/models` share prefixes. Key on the exact pathname, query and
  method.
- **Request bodies** are asserted by parsing the JSON and comparing whole objects.
- **Payload builders** are file-local: a `StartedSession` with all nine keys, a `Message`
  with all eight keys (`kind` null, `settled_at` null for the opening message), a
  `CharacterConfiguration` with all five keys, an `EnabledModel` with a string `server_id`.
  Ids are `"7250000000000000101"`-style strings.
- **Navigation** is observed through the router location (a location probe inside the
  `MemoryRouter`) and, for push versus replace, through history length or Back. It is never
  observed by spying on `useNavigate`.
- **`notifyFailure` / `notifyWarning`** are observed by `vi.mock` of
  `src/shared/notifyFailure` / `src/shared/notifyWarning`.
- **Expected values come from this plan**: the Wire contract, the strings table and the
  decisions. Never call a derivation to compute an expectation.
- **Geometry and drag gestures are `[manual/live]`** (jsdom does not lay out). Keyboard
  drag *activation* is testable (016 conventions).

## Vocabulary

| Term | Means here |
|---|---|
| **opening message** | the composer text sent with the create; stored as the new session's first current-zone row |
| **create-and-seed** | creating the session and inserting the opening message in one transaction |
| **started session** | the route's response: the session's eight keys plus `opening_message` |
| **composer core** | `ComposerCore`: the presentational composer both hosts render |
| **page composer** | `CharacterComposer`: the core on the character page, posting create-and-seed |
| **draft page** | `/characters/new` before the character exists |
| **commit (a field)** | the field losing focus, which triggers its create or save |
| **flush** | saving pending name / persona edits when the screen unmounts |
| **grid** | `MemoLevelGroup`'s opt-in multi-column layout of the same cards |
| **not set** | a character-level configuration value that is null; its resolved value comes from the default |
