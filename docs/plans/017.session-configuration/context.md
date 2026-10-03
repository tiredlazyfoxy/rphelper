# Feature 017 — Session configuration · feature-wide context

## What this feature is

Decides, for any session, which model answers, which system prompt and tool switches
apply, and which RP language and preferred language are in play. Two chains resolve and
share no level (R1):

- **assistant chain**: system prompt and the three tool switches resolve **live**
  `character → session`. The model is **captured** onto the session at creation and is
  read, never re-walked (R4).
- **language chain**: RP language and preferred language resolve `user → session`. The
  character level is skipped because the columns do not exist.

017 adds the configuration columns, captures the model at creation, adds both resolvers
and a use-time model check (no call site until `021`), and adds the roleplayer-facing
routes. On the frontend it adds the `/settings` screen (the two languages plus the user's
own notes), the session header's **model picker** and **tool indicators**, a **session
configuration modal** behind an `IconSettings` gear, and a gate that disables the
composer's Send when the session has no usable model.

The agreed boundary is `brief.md` in this folder. Its Definition and Scope In/Out bound
every step and are **not** widened. Its two open questions are closed by **D5** (one
nullable boolean column per tool) and **D10** (a model override is re-validated when it
is set, and again at use).

## Product ids

`FEAT-013` via **UC-047**, **UC-048**, **UC-049**, **UC-050**, **UC-077**; `FEAT-020`
via **US-092**.

| Criterion | Where it lands |
|---|---|
| US-058.AC-1 (save the user's two language defaults) | `004` (service), `005` (route), `007` (settings form) |
| US-059.AC-1 (no character override → nothing applied; captured model fixed; prompt and tools stay live) | `002` (capture), `003` (live resolution), `005` |
| US-059.AC-2 (character override used by its sessions) | `003`, `004` (character write), `005` |
| US-060.AC-1 (session override wins over character) | `003`, `004` (session write), `005`, `009` / `010` (modal) |
| US-061.AC-1 / AC-2 (languages user → session) | `003`, `004`, `005`, `010` (modal) |
| US-061.AC-3 (no language override at character level) | `001` (no column, no request field), `004`, `005` |
| US-062.AC-1 / AC-2 (tool switches follow the assistant chain) | `003`, `005`, `011` (indicators) |
| US-105.AC-1 / AC-2 (header choice sets the session override, persists) | `004`, `005`, `008`, `011` |
| US-106.AC-1 (no character model → first enabled model) | `002` (capture), `005` |
| US-107.AC-1 / AC-2 (no enabled model → cannot send, told why) | `003` (backend refusal, no call site), `008` (reason), `011` (Send disabled with the reason) |
| US-108.AC-1 / AC-2 (the two chains stated) | `002`, `003`, `005` |
| US-139.AC-1 / AC-2 (character model reaches only new sessions) | `002`, `004` (character write touches no session), `005` |
| US-092.AC-1 (settings screen shows both languages and the user's notes) | `007` |

**Not delivered here, recorded as forward notes, never faked with stand-in tests:**

- **Wiring the use-time check into compose** — `021`. `resolve_model_for_use` (`003`)
  ships with **no call site**, like 006's validators (`llm-and-streaming.md` "Both
  use-time validators ship with no call site"). Before `021` the backend accepts a Send
  (013's non-model append) for any session; the frontend gate (`011`) is UX only.
- **Assembling the resolved prompt, tools and languages into context** — `020`. It reads
  `get_session_configuration` (`003`) rather than re-deriving R1.
- **Removing a disabled tool from the tool list** — `021` / `026` / `027` / `028`. 017
  only resolves the switches.
- **The character page's configuration block** — `018` (brief Out). 017 ships the
  character routes (`005`) with no frontend caller.
- **`model_not_enabled`'s dedicated presentation on a failed compose** (link to the level
  that set it, `frontend-structure.md`) — `021`, where the error first reaches the SPA
  from a use.
- **Translation target = resolved preferred language** (R8) — `023`/FEAT-011's plan.

## Build prerequisites

001..011 are built and committed. 012 is in the working tree (uncommitted). **012..016
are planned, not built.** The roadmap builds in numeric order, so 017 is built after them
and binds to their **declared** interfaces, cited from their step files and not
re-specified.

| Upstream artifact | What 017 relies on | Needed by |
|---|---|---|
| `backend/app/db/schema.py` `users`, `characters`, `sessions`, `llm_servers`, `models` (committed) | the columns 017 adds to; the registry join for enabled models | `001`, `002`, `003` |
| `backend/app/services/llm_registry.py` (committed): `ModelRefLevel`, `EnabledChatModel`, `validate_chat_model`, `UNSET` / `Unset` | the enabled-set rule and the set-time / use-time check | `002`, `003`, `004` |
| `backend/app/errors.py` `ModelNotEnabledError`, `SessionNotFoundError`, `CharacterNotFoundError` (committed) | raised unchanged | `001`, `003`, `004` |
| `backend/app/services/sessions.py` `start_session` (committed, 011) | the creation transaction the capture joins | `002` |
| `backend/app/routers/sessions.py` (committed, 011) | docstring only; its "any PATCH → 405" stays true (D9) | `005` |
| 012 / 015 / 016 `main.py` registrations | 017's router is appended after every router present | `005` |
| 015 `005`–`007`: `app/memosApi.ts`, `app/memoLevelState.ts` (`MemoLevelState(scope, scopeId)`, `loadMemoLevel`), `app/MemoLevelGroup.tsx` (`state`, `title`, `headingOrder`, `onRetry`; 016 `003` adds optional `reorderable`) | the user-notes section of `/settings` | `007` |
| 013 `006` / `007`: `app/Composer.tsx` (`state`, `signal?`), `app/SessionStream.tsx` (`sessionId`), `app/streamState.ts` (`effectiveKind`, `canSend`) | the Send gate (D17) | `011` |
| 011 `009` + 013 `007` + 015 `008` + 016 `006`: `app/SessionScreen.tsx` ready render (header row: character link · start-time heading · setup label · Archived badge · "Open notes"; then `SessionStream`; wall slot with `MemoChainSection`) and its props `{ sessionId, characters, storage }` | the header bar mount (D16) | `011` |
| 008: `app/App.tsx` (`/settings` route element `null`), `app/UserMenu.tsx` ("Settings" item → `/settings`, unchanged) | the settings route | `007` |

- Steps `001`–`005` need only committed backend code (plus 012..016's `main.py`
  registrations for `005`'s append position).
- Step `006` imports only `shared/` modules.
- Step `007` needs **015 `007` delivered** (and 016 `003` if it has landed — D15).
- Steps `008`–`010` import only `shared/` and 017's own modules.
- Step `011` needs **013 `007`, 015 `008` and 016 `006` delivered**.

## Built state this feature reads

- Backend: `app/errors.py` `DomainError` (class-level `code` / `http_status`; subclasses
  set a default message in `__init__`), `register_exception_handlers`;
  `app/models/ids.py` `SnowflakeOut` / `SnowflakeIn`; `app/dependencies.py`
  `require_user` → `CurrentUser(id, username, role)`; `app/db/engine.py`
  `get_connection`; `app/main.py`; `app/db/schema.py`'s one `metadata`, its id column form
  `BigInteger().with_variant(Integer(), "sqlite")`, Text fixed-width timestamps.
  Services take `Connection` first, write inside `with connection.begin():`, read inside
  a private read context that leaves no transaction open, return frozen dataclasses, and
  import no `fastapi`; routers answer with `model_validate(..., from_attributes=True)`.
- Frontend: `src/shared/api.ts` (`apiGet` / `apiPost` / `apiPatch`, path, optional body,
  optional signal; non-2xx → `ApiError`); `src/shared/apiError.ts` (`ApiError` with
  `code`, `status`, `detail`; `isApiError`); `src/shared/IconButton.tsx` (`icon`, `label`,
  `onClick`, `disabled?`, `color?`, `sizeVariant?`); `src/shared/AppProviders.tsx`.
  Pattern references, read and not imported: `app/characterScreenState.ts` (page state
  with `isDirty` / `canSubmit` / `submitSave`, fixed-sentence failures),
  `app/setupDraft.ts` + `app/SetupModal.tsx` (fresh draft per open, conditional mount).

## Wire contract

All 017 routes live in `routers/configuration.py`, router-level `require_user`, full
literal paths (D13). Ids are decimal strings on the wire. Timestamps never appear.

| Route | Body | Answers |
|---|---|---|
| `GET /api/models` | — | 200 `{ models: [EnabledModel…] }` in first-enabled order (D7); `[]` when none |
| `GET /api/me/settings` | — | 200 `UserSettings` |
| `PATCH /api/me/settings` | any subset of `{ rp_language, preferred_language }` | 200 `UserSettings` |
| `GET /api/sessions/{session_id}/configuration` | — | 200 `SessionConfiguration` |
| `PATCH /api/sessions/{session_id}/configuration` | any subset of `{ model, system_prompt, tool_memo_search, tool_session_search, tool_web_search, rp_language, preferred_language }` | 200 `SessionConfiguration` |
| `GET /api/characters/{character_id}/configuration` | — | 200 `CharacterConfiguration` |
| `PATCH /api/characters/{character_id}/configuration` | any subset of `{ model, system_prompt, tool_memo_search, tool_session_search, tool_web_search }` | 200 `CharacterConfiguration` |

Shapes:

```
ModelRef               { server_id: "<decimal>", model_name: string }
EnabledModel           { server_id: "<decimal>", server_name: string, model_name: string }
UserSettings           { rp_language: string | null, preferred_language: string | null }
CharacterConfiguration { model: ModelRef | null, system_prompt: string | null,
                         tool_memo_search: boolean | null, tool_session_search: boolean | null,
                         tool_web_search: boolean | null }
Setting<T>             { session: T | null,                   // the session's own override; null = inherit
                         inherited: T | null,                 // what the level above supplies
                         inherited_level: Level | null,
                         value: T | null,                     // resolved = session ?? inherited
                         level: Level | null }                // who supplied value
Level                  "session" | "character" | "user" | "default"
SessionConfiguration   { model: ModelRef | null,              // the captured reference, unvalidated
                         system_prompt: Setting<string>,
                         tool_memo_search: Setting<boolean>,
                         tool_session_search: Setting<boolean>,
                         tool_web_search: Setting<boolean>,
                         rp_language: Setting<string>,
                         preferred_language: Setting<string> }
```

Level rules: `system_prompt` inherits from `character` (else `inherited` null, level
null); each tool inherits from `character`, else `inherited` true with level `default`, so
a tool's `value` is never null; the two languages inherit from `user` (else null). A
`level` is `session` exactly when `session` is non-null. `user_id` is never on the wire.
`EnabledModel` never carries `base_url`, `kind`, `api_key_ref` or test status.

Request rules (D6, D10): unknown keys are ignored; an absent key changes nothing; an
explicit `null` clears that level (back to inherit). On the session PATCH, `model` may not
be `null` (422) — the session's model is only ever replaced (D10); on the character PATCH
`model: null` clears it. `model` is set as a whole object (`server_id` + non-blank
`model_name`). `rp_language` / `preferred_language` are trimmed and a blank value is
stored as null. `system_prompt` is stored verbatim, and a blank value is stored as null.
An empty or all-unknown body changes nothing and answers the current state.

Failures (`{ error: { code, message, detail } }`):

| Code | Status | When |
|---|---|---|
| `session_not_found` | 404 | session route on a missing or another user's session (011's code) |
| `character_not_found` | 404 | character route on a missing or another user's character (009's code) |
| `model_not_enabled` | 409 | a PATCH whose `model` is not an enabled model now; `detail` `{ server_id: "<decimal>", model_name, level }`, level `session` or `character` by route; **nothing is written** (D10) |
| `no_model_enabled` | 409 | **new** — use-time only (`resolve_model_for_use`, D2); `detail` `{}` |
| `model_not_chosen` | 409 | **new** — use-time only (D2); `detail` `{}` |
| — | 422 | `model: null` on the session PATCH; `model` without a non-blank `model_name` or with a non-numeric `server_id`; a non-boolean tool value; a non-numeric path id |
| `not_authenticated` | 401 | no login cookie |

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

- `docs/architecture/domain-rules.md`: **R1** (two chains sharing no level; lowest
  non-null level wins; NULL is transparent; two resolver functions; no language column on
  `characters`, no model / prompt / tools column on `users`), **R4** (no silent fallback;
  resolution yields an unvalidated reference; validation at use; model captured at
  creation; system prompt and tools live; harmonising either way is a defect; the
  creation-with-no-enabled-model `_TBD:` this plan closes), **R5** (owner scope in SQL; no
  reverse lookup), **R6** (archive is not a lock), **R9** (exactly three tools).
- `docs/architecture/data-model.md`: `users`, `characters`, `sessions` (both `_TBD:`s
  this plan closes), `models` (enabled flag, cascade), Identifiers, timestamps, "Schema
  drift and rebuild".
- `docs/architecture/llm-and-streaming.md`: "The model registry and use-time validation".
- `docs/architecture/backend-structure.md`: "The error model" (the `model_not_enabled`
  row: level `character` or `session`, never `user`), "The per-code status record", "The
  JSON id boundary", "`GET /api/me`" (unchanged), "Persistence access", "Transactional
  DDL" (a read followed by `begin()` on one connection).
- `docs/architecture/workspace-shell.md`: "The model picker", "The ruler and the current
  zone" (US-107 bullet), "The user menu".
- `docs/architecture/frontend-structure.md`: "Routing inside the `app` entry"
  (`/settings`), "State — MobX 6", "Where a store's file lives", "Ids are strings", "The
  API client".
- `docs/architecture/ui-conventions.md`: `IconButton`, the icon table (`IconSettings` for
  both settings surfaces), "Create and edit are always a `Modal`", the MobX draft
  convention, "Async feedback", "Loading, errors and empty states".
- Product: `use-cases/FEAT-013.session-configuration.md`,
  `stories/FEAT-013.session-configuration.md`, `stories/FEAT-020.workspace-shell.md`
  (US-092).

Cited, never copied.

## Files this feature touches

```
backend/
  app/db/schema.py                 # + config columns on characters and sessions       (001)
  app/errors.py                    # + NoModelEnabledError, ModelNotChosenError        (001)
  app/models/configuration.py      # NEW — request / response models                   (001)
  app/services/llm_registry.py     # + enabled-model list + first enabled              (002)
  app/services/sessions.py         # start_session captures the model; docstring       (002)
  app/services/configuration.py    # NEW — resolvers, reads, use-time check (003);
                                   #   session / character / user writes (004)
  app/routers/configuration.py     # NEW — the seven routes                            (005)
  app/main.py                      # registers the configuration router last           (005)
  app/routers/sessions.py          # docstring only                                    (005)
  tests/test_db_schema.py, tests/test_configuration_models.py                          (001)
  tests/test_llm_registry_enabled.py, tests/test_sessions_capture.py,
  tests/test_sessions_service.py   # 011 DoD-16 import guard amended only (D12)        (002)
  tests/test_configuration_resolver.py                                                 (003)
  tests/test_configuration_writes.py                                                   (004)
  tests/test_configuration_router.py                                                   (005)
frontend/
  src/app/configurationApi.ts      # NEW — wire types + five calls                     (006)
  src/app/settingsState.ts         # NEW — settings page state                         (007)
  src/app/SettingsScreen.tsx       # NEW — languages form + "Your notes"               (007)
  src/app/App.tsx                  # /settings renders SettingsScreen                  (007)
  src/app/sessionConfigState.ts    # NEW — header state, model usability               (008)
  src/app/sessionConfigDraft.ts    # NEW — modal draft + submit                        (009)
  src/app/SessionConfigModal.tsx   # NEW — the configuration modal                     (010)
  src/app/SessionConfigBar.tsx     # NEW — picker, tool indicators, gear               (011)
  src/app/SessionScreen.tsx        # owns the state; mounts the bar; feeds the gate    (011)
  src/app/SessionStream.tsx        # passes the gate reason through                    (011)
  src/app/Composer.tsx             # Send gate + reason line                           (011)
  tests/app/configurationApi.test.ts                                                   (006)
  tests/app/settingsState.test.ts, tests/app/SettingsScreen.test.tsx,
  tests/app/App.test.tsx, tests/entries.test.tsx, tests/app/WorkspaceShell.test.tsx    (007)
  tests/app/sessionConfigState.test.ts                                                 (008)
  tests/app/sessionConfigDraft.test.ts                                                 (009)
  tests/app/SessionConfigModal.test.tsx                                                (010)
  tests/app/SessionConfigBar.test.tsx, tests/app/Composer.test.tsx,
  tests/app/SessionScreen.test.tsx, tests/app/App.test.tsx, tests/entries.test.tsx     (011)
```

**Not touched. A step that touches one is out of scope:**

- Backend: `models/sessions.py`, `models/characters.py`, `services/characters.py`,
  `routers/characters.py`, `routers/auth.py` (`GET /api/me` and `IdentityResponse`
  unchanged), `services/users.py`, `services/auth.py`, `dependencies.py`, `ids.py`,
  `models/ids.py`, `db/engine.py`, `db/drift.py`, `db/sync.py`, every 012 / 015 / 016
  module, `tests/conftest.py` (no shared fixtures), `tests/test_sessions_router.py`,
  `tests/test_sessions_models.py` and every 009 character test (the `Session` and
  `Character` wire shapes do not change — D9). No new Python dependency.
- Frontend: `sessionsApi.ts` (its "no update call" note stays true — configuration has
  its own module), `charactersApi.ts`, `sessionScreenState.ts`, `streamState.ts`,
  `UserMenu.tsx`, `WorkspaceShell.tsx`, every memo module (`memosApi.ts`,
  `memoLevelState.ts`, `MemoLevelGroup.tsx`, `MemoChainSection.tsx`), every 016 wall
  module, `src/shared/*`, `src/admin/*`, `src/shell.css`, `src/global.css` (**no
  stylesheet, no selector, no `.css` file**), `vite.config.ts`, `package.json` and the
  lockfile (**no new npm dependency**), `tests/setup.ts`, `tests/conventions.test.ts`,
  `tests/ids-are-strings.test.ts`, `tests/stylesheets.test.ts`.

## Cross-cutting constraints every step holds

**R1 by shape.** `characters` gains no language column; `users` gains nothing. The
character-level resolver input carries no model and no language; the user-level input
carries only the two languages. No request model for the character level accepts a
language key (unknown keys are ignored, so a sent one changes nothing).

**R4: no silent fallback.** Nothing walks from a disabled model to another one. The
resolver never consults the registry. Nothing ever writes `sessions.model_server_id` /
`model_name` except `start_session`'s capture and the session PATCH. A character write
never touches a session row.

**Owner scope lives in SQL (R5).** Every statement reading or writing `sessions`,
`characters` or `users` carries the caller's id in its own predicate. A missing row and
another user's row take the same path. The models list is the instance's shared registry
and carries no user data.

**Routers own HTTP; services own SQL.** No SQL in `routers/configuration.py`; no `fastapi`
import in any service; `models/configuration.py` imports neither routers nor services;
`db/schema.py` imports nothing from `models/` or `services/`. The one service-import
exception is D12.

**Ids are strings in every frontend file and every JSON payload.** `server_id` is a
`string` in TypeScript and never parsed. Two models are the same model when both
`server_id` and `model_name` are equal as strings.

**Pure data contracts.** Data classes hold observable fields only (`makeAutoObservable`);
derivations and effects are free functions taking the state first; effects `runInAction`
after `await`, check `signal?.aborted` before writing, never reject, and write fixed
sentences rather than backend prose. One instance per mount via `useState`, passed as a
prop, no React context, `observer` on every reader. Loads are aborted on unmount;
mutations take no signal (015 D5's posture).

**Never optimistic.** A picker choice, a modal save and a settings save render what the
server returned; a failure leaves the displayed value as the server last said it.

**No notification anywhere in 017.** Every failure has a place of its own (D19).
`notifyFailure` is not imported by any 017 module.

**Every icon-only control goes through `shared/IconButton`.** Tests find controls by
accessible name; the UI strings table is the contract.

**TypeScript only.** No `.js` / `.jsx` / `.mjs` / `.cjs`.

## UI strings — the contract tests bind to

Exact text. Components render these and nothing else for these purposes.

| Where | String | Role / element |
|---|---|---|
| Settings page | heading **"Settings"** | `007` |
| Settings languages | region **"Languages"** with heading **"Languages"**; text inputs **"RP language"**, **"Preferred language"**; each with description **"Used by every session that does not set its own."**; button **"Save"** | `007` |
| Settings load failure | **"Could not load your settings"** + button **"Retry"** | in the "Languages" region (`007`) |
| Settings save failure | **"Could not save your settings."** | inline `Alert` in the "Languages" region (`007`) |
| Settings notes | a `MemoLevelGroup` region **"Your notes"** | `007` (015's group strings apply inside it) |
| Session header bar | group **"Session configuration"** | `011` |
| Model picker | `Select` labelled **"Model"**; option label **"<model_name> (<server_name>)"**; for a captured model that is not enabled, a disabled option **"<model_name> (not enabled)"**; placeholder **"Choose a model"** when none is chosen; placeholder **"No model is enabled"** (picker disabled) when the list is empty | `011` |
| Model change failure | **"That model is no longer enabled."** (409 `model_not_enabled`) / **"Could not change the model."** (anything else) | text under the picker (`008` writes, `011` renders) |
| Tool indicators | group **"Tools"**; badges **"Memo search: on"** / **"Memo search: off"**, **"Session search: on"** / **"… off"**, **"Web search: on"** / **"… off"** | `011` |
| Gear | `IconButton` **"Session configuration"** (`IconSettings`) | `011` |
| Header load failure | **"Could not load the session configuration"** + button **"Retry"** | in the bar (`011`) |
| Send gate reasons | **"Cannot send: no model is enabled on this instance."** / **"Cannot send: choose a model for this session."** / **"Cannot send: this session's model is not enabled. Choose another model."** | text in the composer (`008` produces, `011` renders) |
| Modal | title **"Session configuration"**; buttons **"Save"**, **"Cancel"** | `010` |
| Modal source switches | `SegmentedControl`s labelled **"System prompt"**, **"RP language"**, **"Preferred language"** with options **"Inherit"** / **"Set"**; **"Memo search"**, **"Session search"**, **"Web search"** with options **"Inherit"** / **"On"** / **"Off"** | `010` |
| Modal inputs | `Textarea` **"Session system prompt"**; text inputs **"Session RP language"**, **"Session preferred language"** — rendered only on **"Set"** | `010` |
| Modal inherited lines | **"Inherited from the character:"** followed by the prompt / **"Nothing to inherit: the character has no system prompt."**; **"Inherited from the character: on"** / **"… off"** / **"Inherited: on (default)"**; **"Inherited from your settings: <value>"** / **"Nothing to inherit: no default in your settings."** | `010` |
| Modal client errors | **"Enter a system prompt, or choose Inherit."** / **"Enter a language, or choose Inherit."** | under the field (`009` produces, `010` renders) |
| Modal save failure | **"Could not save the session configuration."** | general `Alert` in the modal (`009`, `010`) |

## Decisions — settled, with their reasoning

"011 Dn" are in `docs/plans/011.rp-sessions/context.md`; "013 Dn" in
`docs/plans/013.stream-and-zone-ui/context.md`; "015 Dn" in
`docs/plans/015.memos/context.md`; "016 Dn" in `docs/plans/016.note-wall/context.md`.

### D1 — What creation captures (user decision 1, refined against US-139.AC-2)

Inside `start_session`'s one transaction, after the character and setup checks:

1. the character has a model configured → that pair is captured **as-is, unvalidated**
   (R4: creation does not consult the registry to approve it);
2. otherwise, at least one model is enabled → the **first enabled model** (D7) is
   captured (US-106.AC-1, US-108.AC-1);
3. otherwise → `model_server_id` / `model_name` stay **NULL**, and stay NULL until the
   roleplayer picks a model in the header. Nothing fills it later on its own.

**Refinement, flagged:** user decision 1 reads "no enabled model at creation → NULL" and
"when at least one is enabled, capture the character's model if set". Taken literally, a
character configured with a model would capture NULL whenever the instance has no
enabled model. **US-139.AC-2 requires a new session to capture the character's
configured model, unconditionally**, and R4 says the capture is not approved against the
registry. So NULL arises only in case 3. Behaviour differs from the literal reading only
when a character has a model and the instance has none enabled; there the session
captures the character's model and reports `no_model_enabled` at use (D2) either way.
Recorded in `outcome.md` for confirmation.

Sessions created before 017 have NULL in both columns (their rows predate the columns)
and behave as case 3: no backfill.

### D2 — The use-time check: `resolve_model_for_use` (user decision 4; check order chosen here)

One backend function takes a session and returns its validated enabled model, or raises,
checking **in this order**:

1. **no model is enabled on the instance at all** → `no_model_enabled` (409), whatever
   the session holds. US-107.AC-2 requires the refusal to say *no model is enabled*, so
   this outranks the session's own state.
2. the session's captured model is NULL → `model_not_chosen` (409).
3. the captured model is not enabled now → `model_not_enabled` (409), level `session`
   (D3), through `validate_chat_model`.

It has **no call site** until `021` wires compose, exactly as 006's validators shipped
(`llm-and-streaming.md`). It is covered by service tests only. Both new errors carry an
empty `detail` and a fixed default message.

### D3 — A captured model reports level `session` (user decision 4; reasoning recorded here)

`model_not_enabled`'s `detail.level` tells the roleplayer where to go to fix it
(`backend-structure.md`). For a captured model the only fix is the header picker. That is a
session-level control, and R4 calls it "the one way the product provides" to change the
model. Pointing at `character` would send the roleplayer to a screen where a change cannot
reach this session (US-139.AC-1). So `session` is the only honest answer, not just the
simplest. The value's origin (character or first enabled) is a creation-time fact and is
not stored. `character` is reported only by the character route's set-time check (D10).

### D4 — `model_ref` encoding: two columns, no FK, both-or-neither (orchestrator decision; closes `data-model.md`'s encoding `_TBD:`)

On both `characters` and `sessions`: `model_server_id` (the registry's id column type,
nullable, **no foreign key**) and `model_name` (Text, nullable), plus a named table CHECK
that both are NULL or both are non-NULL. No FK, because deleting an LLM server must not
cascade into a session or silently null its reference. The dead reference must stay and
raise `model_not_enabled` at use (R4). Two columns rather than one encoded string because
`models` is unique on the pair, and `validate_chat_model` already takes the two values
separately. The literal column names `model_ref` and `tools` stay **forbidden** in the
schema tests. They name the rejected shapes (an opaque single reference, a set-valued tool
column), so asserting their absence keeps those shapes out.

### D5 — Tool switches: one nullable boolean per tool, per level, default on (user decision 2; closes brief open question 1)

`tool_memo_search`, `tool_session_search`, `tool_web_search` (Boolean, nullable, no
default) on `characters` and on `sessions`. Each tool resolves independently,
`character → session`, lowest non-null wins, NULL is transparent. **A tool that no level
sets resolves to enabled**, reported with level `default`. There is no user level for
tools (R1). There are exactly three because R9 closes the set at three, and a fourth tool
is an architecture change that adds a column. A set-valued column would make "inherit
this one tool, override that one" inexpressible.

### D6 — Value normalisation (orchestrator decision; system-prompt rule chosen here)

Languages are free text with no list: trimmed, and blank stored as NULL (= inherit). They
exist only at user and session level. A system prompt is stored **verbatim** (whitespace
can be content, as 015 D15 argues for notes), and a blank one is stored as NULL. Clearing
restores inheritance rather than setting a blank (R1). Normalisation happens in the
request models (`001`), at the wire boundary. Services store what they are given.

### D7 — The enabled set and "first enabled" (orchestrator decision; ordering chosen here)

The **enabled set** is exactly what `validate_chat_model` accepts: `models` rows with
`is_enabled` true whose server row exists. An embedding-designated model that is also
enabled is included, because designation is independent of enablement (`data-model.md`).
Excluding it would make the picker disagree with the validator. **Order:
`llm_servers.id` ascending, then `models.id` ascending.** "First enabled" is the first
row of that list. Reason: it is the order the administrator sees on the LLM Servers page
(`list_servers` orders servers by id, each server's enabled names by `models.id`). So
"first" means the first enabled name on the first server that has one, which the admin
can see without reading SQL. Ordering by `models.id` alone would let a model enabled on a
later server come first because its row happened to be created earlier. The picker lists
in the same order.

### D8 — The resolver: two pure functions with level-restricted inputs, one read (user decision 3, R1)

`services/configuration.py` exposes **`resolve_assistant_chain(character, session)`** and
**`resolve_language_chain(user, session)`**: two functions, not one parameterised one
(R1). Each takes small frozen per-level inputs that only carry what that level may hold.
The character input has system prompt and tools but **no model** (the character's model
matters only at creation, D1) and no language. The user input has only the two
languages. The session's assistant input carries the captured model, which the assistant
chain passes through unchanged and never validates (R4). Each setting resolves to the
`Setting` shape of the Wire contract. **`get_session_configuration`** reads the session,
its character and the caller's user row in one owner-scoped read and applies both
functions. `020` and `021` reuse it.

### D9 — Configuration is its own sub-resource; `Session` and `Character` are unchanged (orchestrator decision, refined here)

The orchestrator suggested widening `SessionResponse` / `CharacterResponse` and adding
`PATCH /api/sessions/{id}`. **Refined:** configuration lives at
`/api/sessions/{id}/configuration` and `/api/characters/{id}/configuration` (GET +
PATCH), and the 8-key `Session` and 6-key `Character` wire shapes are untouched.
Reasons:

- the tree, the sections and the lists never read configuration, and widening the shapes
  would amend 009 / 011 / 013 / 015 / 016 test files (every `Session` literal must grow
  eight required keys to typecheck) for no reader;
- 011's "any PATCH on `/api/sessions/{id}` → 405" and 009's `UpdateCharacterRequest`
  semantics (`None` = not supplied) stay true. The explicit-null-clears rule lives only in
  017's own request models, so one request model never mixes two meanings of `null`;
- the character persona edit carries `024`'s `session_vec` fan-out. A configuration write
  on its own route can never trigger it;
- GET and PATCH answer the same resolved shape, so the header and the modal load one
  thing and a save returns what to render.

### D10 — Set-time validation; the session model is never cleared (orchestrator decision; closes brief open question 2)

A PATCH carrying `model` validates it against the enabled set **before writing, in the
same transaction**: not enabled → `model_not_enabled` (409, level `session` on the
session route, `character` on the character route), and **nothing in the request is
written**. Use-time validation (D2) stays as well, because a model enabled at set time
can be disabled later. The session route does not accept `model: null`. The picker only
chooses, and the captured value moves only through it (`workspace-shell.md` "The model
picker"). The character route accepts `model: null` (clear the override, so future
sessions take the first enabled model). `018`'s UI needs that.

### D11 — Write bookkeeping (orchestrator decision)

A configuration PATCH bumps the row's `updated_at` (fixed-width form) and **never**
`last_used_at`. Configuring a session is not reading-and-working use (011 D3). A PATCH
that changes nothing (empty or all-unknown body) writes nothing and answers the current
state. Archived sessions and characters are configurable (R6: archive is not a lock; 015
D8). The user-settings PATCH bumps `users.updated_at` in the fixed-width form. That is
correct by the convention, and nothing compares that column as text
(`data-model.md`'s known deviation).

### D12 — One narrow service-import exception (planner decision; 011 D11 / 015 D11 precedent)

`services/sessions.py` (capture) and `services/configuration.py` (set-time and use-time
checks) import from `services/llm_registry.py` **only** its transaction-neutral reads
(`list_enabled_chat_models`, `first_enabled_chat_model`, `validate_chat_model`), the
`ModelRefLevel` enum, `EnabledChatModel`, and the `UNSET` / `Unset` sentinel. Those reads
own no transaction, so the rule's reason (a service operation owns its transaction, 010
D6) is untouched. `002` makes each of those reads safe to call **inside a caller's open
transaction and standalone**. `003`'s and `004`'s source tests pin the import list.

011's DoD-16 guard in `tests/test_sessions_service.py` forbids `services/sessions.py`
any `app.services.*` import (011 D11). `002` amends that one test in place (`002`
DoD-11) to allow exactly this exception, and changes nothing else in that file.

### D13 — The route surface (orchestrator decision; one router chosen here)

The Wire contract table, in **one** router `routers/configuration.py`, because routers
group by feature, not by path prefix (015 D9). It is registered in `main.py` **after
every router already present**. Its paths share no shape with existing ones:
`/api/me/settings` is not `/api/me`, and `/configuration` is a new last segment.
`routers/sessions.py`'s docstring, which says nothing is editable, is amended to point
here. `GET /api/models` exists because the admin listing leaks `base_url` and is
admin-only.

### D14 — User settings (orchestrator decision)

`GET` / `PATCH /api/me/settings` carry exactly the two languages. `GET /api/me` and
`IdentityResponse` are unchanged: identity is a gate's input on every boot, and settings
are a page's data. The caller's `users` row always exists under `require_user`, so there
is no not-found path.

### D15 — The settings screen (orchestrator decision; form posture chosen here)

`/settings` renders `SettingsScreen`: a "Settings" heading, a **"Languages"** region with
two text inputs and **Save**, then the user's own notes as a `MemoLevelGroup` titled
**"Your notes"** over a `MemoLevelState("user", null)` (015's forward note). The
languages are edited **on the page**, not in a modal. `frontend-structure.md` routes
`/settings` to "the two languages and the user's own notes", so the page *is* the form.
The character page's persona block (`characterScreenState.ts`) is the precedent: page
state with dirty tracking and an explicit save. The group is **not** `reorderable`.
Reordering is the wall's interaction (016), the wall's "Your notes" group already offers
it, and `@dnd-kit` takes no use beyond its requirement (`frontend-structure.md`).

### D16 — The session header bar (orchestrator decision; placement and states chosen here)

A `SessionConfigBar` sits in the session header **as its last child, after the header's
title row** (the row holding the character link, heading, setup label, Archived badge and
016's "Open notes"), before `SessionStream`. It contains the **model picker** (a Mantine
`Select` labelled "Model", the enabled models in D7 order), the **tool indicators** (one
badge per tool with its resolved state) and the **gear** (`IconSettings`, "Session
configuration") that opens the modal. The picker's value is the **captured** model, never
re-derived from the character (`workspace-shell.md`). A captured model that is not
enabled is shown as a disabled "(not enabled)" option, so the picker never hides what the
session holds. With no model enabled the picker is disabled and says so (US-107). The
bar's data loads when the bar mounts, so 011's loading, not-found and failed renders make
no extra request. A `SessionConfigState` is created at the top of `SessionScreen`, so the
bar and the composer gate read one instance.

### D17 — The Send gate (user decision 4; mechanism chosen here)

`Composer` gains an optional **`sendBlockedReason`** prop (a sentence or null, default
null), passed through `SessionStream`. `SessionScreen` computes it from its
`SessionConfigState`. On the **my turn** position a non-null reason disables Send and is
shown as text in the composer. On **partner**, Send (filing a partner block), the paste
filing and Settle are unaffected, because none of them needs a model. Settle is never
gated. A prop rather than a field or a `canSend` change, because the model's usability is
session-configuration data owned by the screen, not stream data (013 D13), and the prop
leaves `streamState.ts` and its tests untouched. The client check order mirrors D2: no
models → not chosen → not enabled. While either load is pending or failed the usability
is **unknown and Send is not blocked**: a gate that blocks on a failed list would turn a
transient error into a refusal, and the backend check (`021`) is the boundary.

### D18 — The session configuration modal (user decision 3; draft shape chosen here)

The gear opens a Mantine `Modal` with a **fresh `SessionConfigDraft` per open**
(conditional mount, `ui-conventions.md`). Each of the six settings has an explicit
**Inherit** choice and shows the inherited value and where it comes from. Text settings
are Inherit / Set with an input shown on Set. Tools are Inherit / On / Off. On Set, the
input starts from the session's own value, else from the inherited value, else empty.
**Save sends only the keys whose session override changed**, with `null` for Inherit. A
save with no change sends nothing and closes. On success the response replaces the bar's
configuration (no refetch, no toast) and the modal closes. The modal does not carry the
model: the header picker is its one control (UC-077).

### D19 — Feedback (orchestrator posture; as 011 D18 / 015 D5)

Every 017 failure renders where it happened, with a fixed sentence (strings table):
settings load and save in the Languages region, picker failures under the picker, header
load in the bar, modal save in the modal. **No `notifyFailure` call site and no success
feedback** beyond the re-rendered value or the closed modal.

### D20 — Eleven steps

Backend in five: columns + errors + wire models; registry reads + capture; resolver +
reads + use-time check; writes; router. The resolver and the writes are split because
together they exceed 200 LoC. Frontend in six: the API module; the settings screen
(state + component + route, about 190 LoC, kept whole because the state has one consumer);
the header state; the modal draft; the modal; the bar with the screen mount and the
composer gate. The orchestrator's suggested API-layer split for the character routes'
frontend calls is dropped: they have no caller until `018`, and a call with no caller is
dead code.

## Step map

| Step | Subject | Est. LoC | Depends on |
|------|---------|----------|------------|
| 001 | columns on `characters` + `sessions`, two errors, `models/configuration.py` | ~160 | none |
| 002 | `llm_registry` enabled-model reads; capture in `start_session` | ~90 | 001 |
| 003 | `services/configuration.py`: resolvers, `get_session_configuration`, `resolve_model_for_use` | ~150 | 001, 002 |
| 004 | `services/configuration.py`: session / character / user reads and writes | ~160 | 001, 002, 003 |
| 005 | `routers/configuration.py` + `main.py` + `routers/sessions.py` docstring | ~140 | 001–004 |
| 006 | `app/configurationApi.ts` | ~80 | 005 (wire; tests stub `fetch`) |
| 007 | `settingsState.ts` + `SettingsScreen.tsx` + `/settings` in `App.tsx` | ~190 | 006; 015 `007` delivered |
| 008 | `app/sessionConfigState.ts` | ~140 | 006 |
| 009 | `app/sessionConfigDraft.ts` | ~140 | 006 |
| 010 | `app/SessionConfigModal.tsx` | ~150 | 006, 009 |
| 011 | `SessionConfigBar.tsx` + `SessionScreen` / `SessionStream` / `Composer` edits | ~170 | 008, 010; 013 `007`, 015 `008`, 016 `006` delivered |

`003` → `004` are ordered (one file, `004` adds to it). `007` is independent of `008`–`011`.
`008` and `009` are independent of each other.

## Test conventions

Inherited from 011 `context.md` "Test conventions" and 015 `context.md` "Test
conventions": pytest from `backend/`, no shared fixtures, `conftest.py` untouched, schema
from `schema.metadata.create_all` on a file-local engine, per-file `application` /
`client` fixtures, file-local `_insert_user` and `_login`, two users for isolation;
Vitest, `globals: false`, `tests/` mirrors `src/`, `fetch` stubbed per file with
`vi.stubGlobal`, `AppProviders` around rendered components, `MemoryRouter` where routed,
assertions on rendered behaviour only, the `vi.mock` of `src/shared/MarkdownEditor` as a
labelled `<textarea>` wherever a `MemoLevelGroup` renders. Additions for 017:

- **Test names.** Backend: `test_<behavior>__S017_<SSS>_DoD<n>`. Frontend: each `it` title
  ends **`— DoD-N`** of its own step.
- **Registry fixtures.** Enabled models are raw-inserted: an `llm_servers` row (`id`,
  `name`, `kind`, `base_url`, `api_key_ref`, timestamps) and `models` rows (`id`,
  `server_id`, `model_name`, `is_enabled`, `is_embedding_designated`, timestamps). Ids
  are chosen so that `llm_servers.id` order and `models.id` order **disagree** wherever a
  DoD asserts D7's ordering.
- **Expected values come from this plan**: the Wire contract's level rules, D1's capture
  cases, D2's check order, D7's ordering, the strings table. Never call a resolver or a
  derivation to compute an expectation.
- **Stubs by exact path, query and method.** `/api/sessions/<id>`,
  `/api/sessions/<id>/configuration`, `…/entries`, `…/zone`, `…/memo-chain`, `/api/me`,
  `/api/me/settings`, `/api/memos?scope=user` share prefixes; key on the exact pathname,
  query and method.
- **Payload builders** are file-local: a `SessionConfiguration` with all seven keys and
  each `Setting` with all five; `EnabledModel` with string `server_id`
  (`"7250000000000000301"` style).
- **Mantine `Select`** options render in a portal: open the combobox labelled "Model" and
  choose with `screen.getByRole("option", { name })`. **`SegmentedControl`** renders
  radios: choose with `getByRole("radio", { name })` scoped to the control's group.

## Vocabulary

| Term | Means here |
|---|---|
| **assistant chain** | system prompt + three tool switches, `character → session`, live; plus the captured model, read as-is |
| **language chain** | RP language + preferred language, `user → session` |
| **captured model** | `sessions.model_server_id` + `model_name`, written at creation (D1) or by the picker |
| **model ref** | a `(server_id, model_name)` pair; unvalidated until checked |
| **enabled set** | `models` rows with `is_enabled` whose server exists (D7) |
| **first enabled** | the first row of the enabled set in D7 order |
| **override** | a level's own non-null value; NULL = inherit |
| **inherited** | what the level above the session supplies (character, user, or the tools' default) |
| **set-time check** | `validate_chat_model` on a PATCH carrying `model` (D10) |
| **use-time check** | `resolve_model_for_use` (D2) |
| **usability** | the client's mirror of D2: unknown / no models / not chosen / not enabled / usable |
| **gate reason** | the sentence that disables Send on *my turn* (D17) |
