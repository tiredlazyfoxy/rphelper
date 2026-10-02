# Feature 009 — Characters · outcome

Intended changes to `docs/architecture/` once this feature ships, for the architect to
apply at finalization. Grouped by target file. Decisions referenced as D-n are in this
folder's `context.md`.

## `docs/architecture/data-model.md`

| Section | Intended change | Reason |
|---|---|---|
| `characters` | Add an **"As built by FEAT-006 (plan 009)"** block. The column list is delivered **in two parts**: 009 declares `id`, `user_id` (FK `users.id`, NOT NULL, no `ON DELETE`), `name`, `sheet` (Text NOT NULL, no server default; `""` when omitted), `archived_at` (nullable), `created_at`, `updated_at`, plus one index on `user_id`. **`model_ref`, `system_prompt`, `tools` arrive with `017`**, whose plan fixes their encodings. Existing databases pick up 017's columns through the drift page's **Sync**, and pick up the 009 table itself through **Create** (D5). | The doc lists ten columns as one shape. Without this note, a reader of the 009-built registry sees three missing columns as drift or a defect. |
| `characters` | Record that `sheet` is **one markdown body** (the persona), not a set of fields (D2). | Closes `brief.md`'s open question 1; the doc said "markdown" without saying it is the whole persona. |
| "`translations`, `messages`, `memos` and the archive rule" (or `characters`) | Record the as-built archive semantics: archive is idempotent and keeps the original `archived_at`; restore sets NULL; a no-op writes nothing (no `updated_at` bump); editing an archived character is allowed and leaves `archived_at` unchanged (D9). | R6 fixes the behaviour but not the idempotency or edit-while-archived postures; `010` and `011` should match them. |
| Vector tables — the `session_vec` fan-out paragraph | Forward note: `services/characters.py`'s `update_character` is the persona write that the `session_vec` fan-out will hook. **The feature that creates `session_vec`** must add the invalidation there. 009 has no vector write because no session or vector table exists. | The doc says a persona edit invalidates every session vector under the character; the write path now exists without that hook, and nothing else will point at it. |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| New subsection beside the admin route surfaces — **"The characters route surface — FEAT-006"** | Add the route table from `context.md`'s Wire contract: `GET` / `POST /api/characters` (with `include_archived`), `GET` / `PATCH /api/characters/{character_id}`, `POST …/archive`, `POST …/restore`, all behind **router-level `require_user`**, and **no `DELETE` (405)**. Record the decisions: named action routes for archive/restore, `PATCH` for name/sheet with null ≡ absent and an empty PATCH a no-op (D7); the wrapped list response `{ characters: [...] }`; the interim order (below). | The first roleplayer-owned route family; `010` / `011` will copy its shape and its R5 posture. |
| "The error model" — the named-errors table | Add `character_not_found`: raised when a character route addresses an id that does not exist **or belongs to another user**; `detail` empty; FEAT-006, UC-018, UC-067. | New code. |
| "The per-code status record" | Add `character_not_found` → **404**: the path's id addresses no row *for this caller*; another user's row answers identically to a nonexistent one, so existence never leaks (R5, D8). Introduced by plan 009. | The status record is per code, added by the feature that introduces it. |
| "Authorization as router dependencies" | Note `routers/characters.py` as `require_user`'s first router-level use, and that an administrator owns characters like any account, scoped by its own id (D6). | The table says "all roleplayer routers" without a built example; the admin-owns-characters consequence is non-obvious. |
| "The JSON id boundary" or "Routers versus services" | Record the validation posture: a blank or whitespace-only `name` is stripped and refused by pydantic (**native 422, no domain code**), matching the admin-users models; unknown body keys are ignored (D8). | Sets the precedent for every later roleplayer form. |

## `docs/architecture/domain-rules.md`

| Section | Intended change | Reason |
|---|---|---|
| R6 | Add one sentence: as built for characters (plan 009), the listing flag is `include_archived=true`, a by-id read answers archived rows, and archive/restore are idempotent (D9). | R6 says "an explicit flag" without naming it; `010` / `011` should reuse the same name. |

## `docs/architecture/frontend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| "Routing inside the `app` entry" — the archive-toggle `_TBD:` | **Settle it for FEAT-006**: the toggle is a **"Show archived" switch in the tree's header**, not persisted; when on, archived characters appear in the tree dimmed with an "Archived" badge; an archived character's page `/characters/:id` stays reachable directly and offers Restore in place of Archive (D4). Leave the `_TBD:` open **for setups and sessions only** (`010`, `011`). | The `_TBD:` asked FEAT-006's plan to place it. |
| "Routing inside the `app` entry" — `/characters/new` | Record the interim: 009 renders `/characters/new` as a form with an explicit **Create** that navigates (with `replace`) to `/characters/<id>`; **`018` replaces Create with save-on-first-input** on the same route (D1). | The route is described as the draft page; until 018 it is not. |
| "Markdown" | Record the shared editor: `src/shared/MarkdownEditor.tsx`, a label / markdown `value` / `onChange(markdown)` / `readOnly` wrapper over `@mantine/tiptap` + `tiptap-markdown`, **TipTap pinned to major 2** (both peers bind to it), stylesheet imported by the component. Every markdown editing surface (`015` notes, `017` user notes, `018`) reuses it. Note that **`react-markdown` is not yet a dependency** (D3). | Names the one wrapper so later features do not fork a second editor; records the version pin that otherwise breaks on a routine install. |
| "The multi-entry build" — the `shared/` comment | Add `MarkdownEditor` to the list of `shared/` modules. | New shared module. |
| "State — MobX 6" / "Where a store's file lives" | Record the workspace-level state precedent: one `CharactersState` created in `App` and passed to both the tree and the character screen; mutations apply the server's returned row through one upsert rule rather than refetching the list (D11). | The first state shared by two regions of the shell; `011` extends it with sessions. |

## `docs/architecture/workspace-shell.md`

| Section | Intended change | Reason |
|---|---|---|
| "The three columns" | Record the tree as built by 009: header with "Search" (`IconSearch`), "New character" (`IconPlus`) and the "Show archived" switch; one row per character, a router link marked `aria-current="page"` on its route; **no chevron and no session rows yet** (`011` adds the session level, the `IconChevronDown` expand/collapse and the newest-use order) (D13). | The doc describes the finished two-level tree; this records the delivered first level. |
| "The character page" | Record what 009 delivers: name, persona editor, labelled **Save** (`IconDeviceFloppy`), **Archive** / **Restore**, the Archived badge, and an empty **Sessions** heading; loading / "Character not found" / failed-with-Retry states. Notes grid (`015`), setups (`010`), resolved configuration (`017`), composer (`018`) and the draft-page flow (`018`) remain. Record that the persona is saved with an **explicit Save**, not blur-save (D2). | Partial delivery. The explicit-save choice differs from the workspace's blur-save and should read as decided. |

## `docs/architecture/ui-conventions.md`

| Section | Intended change | Reason |
|---|---|---|
| Icon table | Record the as-built uses: Archive / Restore (`IconArchive` / `IconArchiveOff`) and Save (`IconDeviceFloppy`) as **left sections of labelled buttons** on the character screen; "Search" / "New character" `IconButton`s in the tree header with the same labels as the rail. | Labels are the accessible names tests bind to. |
| "Async feedback" | Add the character screen and tree as worked examples of "a failure with a place of its own": every 009 failure renders inline (screen `Alert`, tree text + Retry, "Character not found"), and 009 adds no `notifyFailure` call site (D12). | A second app-entry example of the boundary. |
| "The confirm convention" — "Deliberately NOT confirmed" | Add **archiving a character** (and by extension setups / sessions): non-destructive, reversible by Restore. | Reads as decided rather than forgotten. |

## Forward notes (not architecture changes; for the owning plans)

- **`011` (sessions):** keep an **archived character's sessions reachable by direct URL**.
  R6 says nothing is destroyed, and 009 already keeps the archived character's own page
  reachable (brief open question 2). This is a recommendation, not a requirement. `011`
  also adds the tree's session level, the per-character chevron, and **replaces D10's
  interim `created_at DESC` order with newest session use** (US-089), and fills the
  character screen's empty "Sessions" section.
- **`018` (character page):** swaps `/characters/new`'s explicit Create for
  save-on-first-input with a draft marker (UC-017 step 2/4, UC-074, US-097), and adds
  the notes grid and composer around 009's name / persona / archive controls. It may
  revisit explicit Save versus blur-save.
- **`017` (configuration):** adds `model_ref`, `system_prompt`, `tools` to the
  `characters` Table literal; existing databases reach them through Sync.
- **US-021.AC-2 is not delivered** ("a later session under that character uses the
  updated persona"). It needs sessions (`011`) and context composition (`020`). No
  stand-in test was written. FEAT-006 is **partially delivered** until then.


## Observations

- Step 002: `services/characters.py` is the third service to carry its own private copy of
  `_now_text()` and the second to carry the `_reading` read-rollback context manager
  (after `llm_registry.py`). The duplication is the convention today, not an accident;
  possible impact: `backend-structure.md` could name both idioms explicitly under the
  service-module section so each new service copies them deliberately.

- Step 003: `include_archived` on `GET /api/characters` is the **first query parameter in
  any router** — before it, every admin router's docstring asserted "no query parameter
  exists anywhere on this router". It also forces the frozen parameter order (the only
  defaulted parameter must come last, after the `Annotated[..., Depends(...)]` ones).
  Possible impact: `backend-structure.md` could add a short query-parameter rule to its
  router section (plain typed parameter with a default, placed last, no `Query(...)`
  wrapper) so the next router does not re-derive it.

- Step 004: the workspace characters store is the repo's **second** list-store shape.
  `usersPageState` keeps `status: "idle" | "loading" | "ready"` plus an `errorMessage`
  string and guards the loading write with `if (state.status !== "ready")`;
  `charactersState` uses a four-value ladder with an explicit `"failed"`, no message field
  (D12 gives every failure its own place in the UI) and an unconditional `"loading"` write
  so a retry shows loading. Possible impact: `frontend-structure.md` could name the
  status-ladder form as the convention for new list stores and say which of the two a new
  store should copy, so the next one does not pick by accident.

- Step 005: the TipTap wrapper's "never echo" rule rests on two library defaults that both
  go the wrong way: `editor.setEditable(editable)` defaults `emitUpdate` to **true**, and
  `editor.commands.setContent(content)` must be given `emitUpdate: false` explicitly.
  Either default alone makes `onChange` fire on mount. Possible impact:
  `frontend-structure.md`'s "Markdown" section could state the rule for every future
  consumer of `shared/MarkdownEditor` (and for `015` / `017` / `018`, which reuse it):
  `onChange` is emitted from `onUpdate` only, and every programmatic content or
  editability write passes `emitUpdate` false.

- Step 006: four submit effects in one module now repeat the same shape (in-flight guard →
  `runInAction` setting `"submitting"` and clearing `error` **before** the request →
  try/catch with the two abort checks → `finally` returning to `"idle"` unless aborted →
  success handling after the try/finally, so the server's row is applied only once the
  state is back to idle). Archive and restore share a private helper; create and save
  cannot, because each writes a different slice (draft adopted vs draft preserved).
  Possible impact: `frontend-structure.md` could name this submit-effect shape as the
  convention (it is `admin/createUserDraft.ts`'s shape generalised) so `010`'s setups
  screen and the later per-screen states copy it rather than re-deriving the abort and
  finally rules.

- Step 007: with the state classes holding observable fields and no methods, a form
  component binds a field by assigning it inside `runInAction` at the input's `onChange`
  (`runInAction(() => { state.name = value; })`) — the alternative, a pair of setter free
  functions per field in the state module, adds a function per field for the same effect.
  Possible impact: `frontend-structure.md`'s MobX section could state the binding rule
  ("components write draft fields through `runInAction`; state modules export derivations
  and effects, not setters") so `010`'s setups screen and the later form screens bind the
  same way instead of each choosing.

- Step 008: the tree's "Archived" badge sits in the row **next to** the `NavLink`, not
  inside it, so the link's accessible name stays exactly the character's name while the
  row still reads as archived; and the list's role/name come from a bare
  `Box component="ul" aria-label="Characters"` whose only presentation is an inline
  `listStyle: "none"` (there is no stylesheet to put a list reset in — `shell.css` is
  layout-only and no new `.css` is allowed). Possible impact: `ui-conventions.md` could
  state both rules (status badges live beside the link, never in it; a named list is a
  `ul` + `aria-label`) so `011`'s session level and `010`'s setups list render the same
  shape.
