# Feature 009 — characters

| Step | File                                   | Status  | Verifier | Date |
|------|----------------------------------------|---------|----------|------|
| 001  | `001.table-error-models.md`            | done    | PASS     | 2026-10-02 |
| 002  | `002.characters-service.md`            | done    | PASS     | 2026-10-02 |
| 003  | `003.characters-router.md`             | done    | PASS     | 2026-10-02 |
| 004  | `004.characters-api-and-state.md`      | done    | PASS     | 2026-10-02 |
| 005  | `005.markdown-editor.md`               | done    | PASS     | 2026-10-02 |
| 006  | `006.character-screen-state.md`        | done    | PASS     | 2026-10-02 |
| 007  | `007.character-screen-and-routes.md`   | done    | PASS     | 2026-10-02 |
| 008  | `008.character-tree.md`                | done    | PASS     | 2026-10-02 |

## Files Changed

### Step 001 — the `characters` table, its not-found error and its pydantic models
- `backend/app/db/schema.py` — `characters` Table literal: seven columns, `users.id` FK with no `ON DELETE`, one non-unique `user_id` index (verified against D5; no change needed)
- `backend/app/errors.py` — `CharacterNotFoundError` (`character_not_found`, 404, empty `detail`), `UserNotFoundError` shape (verified; no change needed)
- `backend/app/models/characters.py` — the four wire models; stripped non-empty `name`, verbatim `sheet`, `extra="ignore"` on both requests (verified against the Wire contract and D7/D8; no change needed)

All three files were already complete and correct as written by the skeleton — this step
verified them against D5, D7, D8 and the Wire contract and changed no source.

### Step 002 — the characters service
- `backend/app/services/characters.py` — filled the six frozen operations: owner-scoped SQL
  in every statement (`user_id` in each `WHERE`, in the insert's `VALUES`, and in each
  UPDATE's own `WHERE`, not only the locating read), D10 order
  (`created_at DESC, id DESC`), D9 archive/restore no-ops that write nothing, PATCH
  semantics with `None` = not supplied, and private helpers `_character_select`,
  `_to_character`, `_owned_update`, `_require_character`, `_fetch_existing`, `_reading`
  (the read-rollback context manager) and the module's own `_now_text`. No removal
  operation and nothing HTTP-shaped imported.

### Step 003 — the `/api/characters` router
- `backend/app/routers/characters.py` — filled the six frozen handler bodies and
  `_to_response`: each calls its service operation with `current_user.id` as `user_id` and
  converts through `CharacterResponse.model_validate(..., from_attributes=True)` (the
  repo's uniform conversion), timestamps passed through as text. PATCH forwards
  `body.name` / `body.sheet` as-is, so an omitted field and an explicit `null` are both the
  service's "not supplied" (D7). The six service operations were added to the existing
  `app.services.characters` import. No SQL, no try/except (`CharacterNotFoundError`
  reaches `main.py`'s `DomainError` handler), no `DELETE` route.
- `backend/app/main.py` — verified only: the skeleton's `characters_router` import and its
  single `include_router` after `admin_db_router` were already in place and correct; this
  step changed nothing in the file.

### Step 004 — the characters API client and the workspace characters state
- `frontend/src/app/charactersApi.ts` — filled the six calls over `shared/api`'s
  `apiGet` / `apiPost` / `apiPatch` plus the pure `isArchived`. `fetchCharacters` appends
  `?include_archived=true` only when the flag is true and unwraps the payload's
  `characters`; `updateCharacter` builds a body holding exactly the supplied keys; the id
  routes go through one private `characterPath` helper (`encodeURIComponent`, never
  parsed). All client `ApiError`s propagate unchanged.
- `frontend/src/app/charactersState.ts` — filled `loadCharacters` (sets `"loading"`
  unconditionally, requests with `includeArchived` = `showArchived`, writes the server's
  rows in order with `"ready"`, writes `"failed"` and keeps the rows on failure, returns
  without writing on an aborted signal, never rejects), `setShowArchived` (flag only, no
  request) and `applyCharacter` (D11's three cases: replace in place, remove/skip when
  archived while hidden, else insert before the first row whose `created_at` is less than
  the new row's — string compare, no id ordering). Added the `runInAction` import and the
  private `isAbortRejection` / `isVisible` helpers; the class is untouched.

### Step 005 — the shared markdown editor
- `frontend/src/shared/MarkdownEditor.tsx` — filled the frozen `MarkdownEditor` body:
  `useEditor` with `[StarterKit, Link, Markdown]`, `content: value` (parsed as markdown by
  `tiptap-markdown`), `editable: !readOnly`, and `editorProps.attributes`
  (`role="textbox"`, `aria-label={label}`, `aria-multiline="true"`) so the three land on
  the ProseMirror contenteditable itself. `onChange` is reached only from `onUpdate`
  through a ref (user edits only, no echo); an external `value` is applied with
  `editor.commands.setContent(value, false)` and only when it differs from
  `editor.storage.markdown.getMarkdown()`; `readOnly` drives
  `editor.setEditable(!readOnly, false)` in an effect keyed on it. Toolbar
  (Bold/Italic · H2/H3 · BulletList/OrderedList · Link/Unlink in four
  `RichTextEditor.ControlsGroup`s) renders only when editable; `RichTextEditor.Content` is
  always the surface. A null `editor` (first render) is handled: both effects early-return
  and every Mantine part is null-safe. Signature, props type and the stylesheet import are
  unchanged.
- `frontend/package.json` / `frontend/package-lock.json` — no change needed: the six
  packages were already installed at the frozen versions by the skeleton step.

### Step 006 — the character screen's state
- `frontend/src/app/characterScreenState.ts` — filled every frozen derivation and effect
  body behind the unchanged signatures. `isNewCharacter` / `isDirty` / `canSubmit` are
  pure (the draft name is trimmed only to decide "blank"; `canSubmit` also requires no
  submit in flight and new mode or a dirty draft). `loadCharacter` sets `"loading"` first
  (so a retry shows loading), `fetchCharacter`s by id, and on success writes `character`
  plus the draft and `"ready"`; an `ApiError` with code `character_not_found` sets
  `"not-found"`, anything else `"failed"`. `submitCreate` / `submitSave` /
  `submitArchive` / `submitRestore` follow `createUserDraft.ts`'s control flow: a guard,
  a `runInAction` setting `"submitting"` and clearing `error` **before** the request, a
  try/catch with the abort checks, a `finally` returning to `"idle"` unless aborted, and
  the success handling after it. Create applies the row then calls `onCreated(id)`; Save
  replaces `character` **and** the draft with the response then applies it; Archive and
  Restore share one private `submitAction` helper that replaces `character` only, leaving
  unsaved draft edits intact (D9). Failures set the four exact sentences; nothing is
  written before the response (never optimistic), the name is sent as typed, ids stay
  strings, and the module imports no `@mantine/notifications` and no router. Added
  imports: `runInAction`, `isApiError`, the five `charactersApi` calls and
  `applyCharacter`.

### Step 007 — the character screen and its two routes
- `frontend/src/app/CharacterScreen.tsx` — filled both frozen bodies. `CharacterScreen`
  creates its `CharacterScreenState` once with `useState(() => …)`, loads on mount in
  existing mode through an `AbortController` held in a ref (aborted on unmount; its signal
  is reused by Retry), and renders by mode and status: new mode ("New character", Name,
  Persona, `IconPlus` **Create** disabled unless `canSubmit`, whose `onCreated` does
  `void navigate` to `/characters/<the returned id>` with `{ replace: true }`, the id
  string used verbatim —
  D1), existing `"loading"` (a `Center`ed `Loader`), `"not-found"` ("Character not found",
  no retry), `"failed"` ("Could not load the character" + "Retry" re-running
  `loadCharacter`), and `"ready"` (the **saved** `character.name` heading, the "Archived"
  badge from `isArchived`, the draft-bound Name/Persona, `IconDeviceFloppy` **Save**
  disabled unless `canSubmit`, `IconArchive` **Archive** or `IconArchiveOff` **Restore**
  disabled while submitting, then an empty "Sessions" heading). The draft writes are
  `runInAction` assignments in the component (006's module is not in scope, so no setters
  were added there); every submit is `void`-ed from its handler; a non-null `error` renders
  in an inline Mantine `Alert` above the form and nothing is notified (D12). Layout is a
  Mantine `Container` + `Stack`; no `.css` added and no `shell.css` change.
  `CharacterRoute` reads `useParams().id` as a string (never parsed) and renders
  `CharacterScreen` keyed by it.
- `frontend/src/app/App.tsx` — the three frozen wiring changes (`useState(() => new
  CharactersState())` and the two character-route elements) were already in place from the
  skeleton and are unchanged; this step only corrected one stale clause in the doc comment
  ("each an empty centre column"), since the two character routes are no longer empty.

### Step 008 — the character tree's header and character level
- `frontend/src/app/CharacterTree.tsx` — filled the frozen `CharacterTree` body. One
  `useEffect` keyed on the state and on the `showArchived` value read during render loads
  the list through a fresh `AbortController` (aborted by the cleanup on the next run and on
  unmount, its signal reused by Retry); the switch's handler only calls `setShowArchived`,
  so a toggle issues exactly one request (D4). The header is the "Search" (`IconSearch` →
  `/search`) and "New character" (`IconPlus` → `/characters/new`) `IconButton`s plus the
  "Show archived" Mantine `Switch` (D13 — no chevron, no session rows). The level renders a
  small `Loader` for `"idle"` and `"loading"`, inline "Could not load characters" + "Retry"
  for `"failed"` (no notification — D12), and for `"ready"` a `Box component="ul"`
  `aria-label="Characters"` with one `li` per character in state order: a Mantine `NavLink`
  `component={Link}` `to={`/characters/${id}`}` (id verbatim, never parsed) labelled with
  the name, `c="dimmed"` and followed by a gray `Badge` "Archived" when archived, and
  `active` + an explicit `aria-current="page"` on the row whose id equals
  `useMatch("/characters/:id")`'s — read from the location because the tree sits outside
  `<Routes>`, with `/characters/new` excluded so it matches no row. An empty list renders no
  rows and no placeholder. No `.css` added and no `shell.css` change.
- `frontend/src/app/WorkspaceShell.tsx` — no edit needed: the skeleton's required
  `characters` prop and the `<Box flex={1}><CharacterTree characters={characters} /></Box>`
  body (between "Collapse tree" and the `UserMenu` footer, inside the one nav column) are
  already the frozen wiring; the rail branch, overlay effects, collapse persistence and the
  two-child `.app` grid are untouched.
- `frontend/src/app/App.tsx` — no edit needed: the one `CharactersState` created in 007 is
  already passed as `characters={characters}` to `WorkspaceShell`, so the tree and the
  character screen share it (D11).

## Skeleton

### Step 001 — frozen interface (2026-10-02)

- `backend/app/db/schema.py` — `characters = Table("characters", metadata, ...)` — new.
  Columns in order: `id` (`BigInteger().with_variant(Integer(), "sqlite")`, `primary_key=True`,
  `autoincrement=False`), `user_id` (same int type, `ForeignKey("users.id")` with no `ondelete`,
  `nullable=False`), `name` (`Text`, `nullable=False`), `sheet` (`Text`, `nullable=False`, no
  server default), `archived_at` (`Text`, `nullable=True`), `created_at` (`Text`,
  `nullable=False`), `updated_at` (`Text`, `nullable=False`). Plus
  `Index("ix_characters_user_id", "user_id")` declared inside the `Table(...)` call, non-unique.
- `backend/app/errors.py` — `class CharacterNotFoundError(DomainError)` — new.
  `code = "character_not_found"`, `http_status = 404`,
  `__init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None`
  defaulting `message` to `"That character does not exist."` (the `UserNotFoundError` shape).
  `detail` stays `{}` unless passed.
- `backend/app/models/characters.py` — `class CharacterResponse(BaseModel)` — new.
  Fields: `id: SnowflakeOut`, `name: str`, `sheet: str`, `archived_at: str | None`,
  `created_at: str`, `updated_at: str`. No `model_config`. Timestamps are the stored
  fixed-width text, passed through as `str` (not `datetime`).
- `backend/app/models/characters.py` — `class CharacterListResponse(BaseModel)` — new.
  Field: `characters: list[CharacterResponse]`.
- `backend/app/models/characters.py` — `class CreateCharacterRequest(BaseModel)` — new.
  `model_config = ConfigDict(extra="ignore")`;
  `name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]` (required);
  `sheet: str = ""` (verbatim, never stripped).
- `backend/app/models/characters.py` — `class UpdateCharacterRequest(BaseModel)` — new.
  `model_config = ConfigDict(extra="ignore")`;
  `name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None`;
  `sheet: str | None = None`. Absent or explicit `null` both mean "not supplied"; which keys
  were sent is `model_fields_set`.
- Caller-compile edits (out of Source-files scope): None.

Notes for later steps: the four model names, `CharacterNotFoundError` and the `characters`
table are the frozen names `002`/`003` bind to. `StringConstraints` is this repo's first use;
it is imported from `pydantic` in `app/models/characters.py`.

### Step 002 — frozen interface (2026-10-02)

All in `backend/app/services/characters.py` (new file). Bodies raise `NotImplementedError`.

- `@dataclass(frozen=True) class Character` — new. Fields in order: `id: int`, `name: str`,
  `sheet: str`, `archived_at: str | None`, `created_at: str`, `updated_at: str`. No `user_id`;
  timestamps are the stored fixed-width text as `str`, matching `001`'s response models.
- `def list_characters(connection: Connection, user_id: int, include_archived: bool = False) -> list[Character]`
  — new. `include_archived` defaults to `False` so "without the flag" (DoD-4) is a two-argument call.
- `def create_character(connection: Connection, generator: SnowflakeGenerator, user_id: int, name: str, sheet: str) -> Character`
  — new. Generator second (the `users.create_user` shape), `user_id` third; `sheet` is required,
  the router passes the request model's `""` default.
- `def get_character(connection: Connection, user_id: int, character_id: int) -> Character` — new.
- `def update_character(connection: Connection, user_id: int, character_id: int, name: str | None = None, sheet: str | None = None) -> Character`
  — new. `None` = not supplied, for both.
- `def archive_character(connection: Connection, user_id: int, character_id: int) -> Character` — new.
- `def restore_character(connection: Connection, user_id: int, character_id: int) -> Character` — new.

Imports frozen at the module level: `dataclass` from `dataclasses`, `Connection` from `sqlalchemy`,
`SnowflakeGenerator` from `app.ids`. `characters` (from `app.db.schema`) and `CharacterNotFoundError`
(from `app.errors`) are **not** imported yet — an unused import fails `ruff` (F401); the coder adds
both when filling the bodies. No private helpers are frozen: `_now_text`, the `Select[...]` projection
factory, the `Row[...]` mapper and the read-rollback helper are the coder's, per `002.context.md`.

The character-id parameter is named `character_id` in all four id-addressed operations — step `003`'s
router binds to that name. There is no delete operation and the module's source text contains neither
`delete` nor `fastapi` as substrings (DoD-11).

- Caller-compile edits (out of Source-files scope): None — the module is new and has no callers yet.

### Step 003 — frozen interface (2026-10-02)

`backend/app/routers/characters.py` (new file). Every handler body raises
`NotImplementedError`; the decorators, paths, methods, status codes, parameter types and
return types are the frozen contract.

- `router = APIRouter(prefix="/api/characters", tags=["characters"], dependencies=[Depends(require_user)])`
  — new. Router-level guard per **D6**; `tags` follows the `admin_users` shape.
- `def _to_response(character: Character) -> CharacterResponse` — new, private. The one
  `Character` → wire conversion; timestamps pass through as `str`, never parsed.
- `@router.get("", status_code=200)`
  `def list_own_characters(current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)], include_archived: bool = False) -> CharacterListResponse`
  — new. `include_archived` is a plain FastAPI **query** parameter (first in the repo; no
  in-repo precedent) and must stay last, being the only parameter with a default.
- `@router.post("", status_code=201)`
  `def create_own_character(body: CreateCharacterRequest, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)], generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)]) -> CharacterResponse`
  — new. The only handler taking the generator.
- `@router.get("/{character_id}", status_code=200)`
  `def read_own_character(character_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> CharacterResponse`
  — new.
- `@router.patch("/{character_id}", status_code=200)`
  `def update_own_character(character_id: SnowflakeIn, body: UpdateCharacterRequest, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> CharacterResponse`
  — new.
- `@router.post("/{character_id}/archive", status_code=200)`
  `def archive_own_character(character_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> CharacterResponse`
  — new.
- `@router.post("/{character_id}/restore", status_code=200)`
  `def restore_own_character(character_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> CharacterResponse`
  — new.
- `backend/app/main.py` — `create_app()` gains `app.include_router(characters_router)` as the
  **last** `include_router`, after `admin_db_router`, plus
  `from app.routers.characters import router as characters_router` in the alphabetised
  router-import block (between `bootstrap` and `health`). Signature unchanged; nothing else
  in the file changed.
- Caller-compile edits (out of Source-files scope): None.

Notes for the coder:

- **Handler names deliberately differ from the service names.** The six service operations
  (`list_characters`, `create_character`, `get_character`, `update_character`,
  `archive_character`, `restore_character`) are imported by name in the repo's router style;
  naming a handler identically would be an `F811` redefinition. Hence the `_own_` handler
  names above — they are frozen, so the coder imports the service names unaliased.
- **No service import is frozen.** The stub imports only `Character` from
  `app.services.characters` (used by `_to_response`'s signature); importing the six
  operations now would fail `ruff` F401. The coder adds them when filling the bodies.
- **No `DELETE` handler**, by contract (R6, US-086.AC-3). Starlette answers 405 for `DELETE`
  on `/api/characters` and `/api/characters/{character_id}` on its own; adding any delete
  route breaks DoD-9.
- The router catches nothing: `CharacterNotFoundError` reaches `main.py`'s registered
  `DomainError` handler, and a blank `name` is the request models' native 422.
- Verified by importing the module: the six routes register as `GET|POST /api/characters`,
  `GET|PATCH /api/characters/{character_id}` and
  `POST /api/characters/{character_id}/archive|restore` with 200/201 as frozen.

Gates after this step: `mypy app` — Success, 42 source files; `ruff check .` — All checks
passed. (`pytest` not run: step 001's DoD-11/DoD-12 leave two existing tests knowingly red
until the test-coder rescopes them.)


### Step 004 — frozen interface (2026-10-02)

Both files new, under `frontend/src/app/`. Every function body throws
`new Error("not implemented: <name>")`; the types and signatures are the frozen contract.

`frontend/src/app/charactersApi.ts`:

- `export type Character = { id: string; name: string; sheet: string; archived_at: string | null; created_at: string; updated_at: string }` — new. Field-for-field the wire object; no renaming layer, `id` is a decimal string.
- `export type CharacterListResponse = { characters: Character[] }` — new. The listing envelope `fetchCharacters` unwraps.
- `export type CreateCharacterInput = { name: string; sheet: string }` — new. Both keys always sent (DoD-2).
- `export type UpdateCharacterPatch = { name?: string; sheet?: string }` — new. Only the supplied keys are sent.
- `export function isArchived(character: Character): boolean` — new, pure.
- `export async function fetchCharacters(includeArchived: boolean, signal?: AbortSignal): Promise<Character[]>` — new. Resolves to the unwrapped array.
- `export async function fetchCharacter(characterId: string, signal?: AbortSignal): Promise<Character>` — new.
- `export async function createCharacter(input: CreateCharacterInput, signal?: AbortSignal): Promise<Character>` — new.
- `export async function updateCharacter(characterId: string, patch: UpdateCharacterPatch, signal?: AbortSignal): Promise<Character>` — new.
- `export async function archiveCharacter(characterId: string, signal?: AbortSignal): Promise<Character>` — new.
- `export async function restoreCharacter(characterId: string, signal?: AbortSignal): Promise<Character>` — new.

`frontend/src/app/charactersState.ts`:

- `export type CharactersLoadStatus = "idle" | "loading" | "ready" | "failed"` — new.
- `export class CharactersState` — new. Observable fields only, in order: `characters: Character[] = []`, `status: CharactersLoadStatus = "idle"`, `showArchived = false`. Constructor is exactly `makeAutoObservable(this, {}, { autoBind: true })`. No methods, no computed getters.
- `export async function loadCharacters(state: CharactersState, signal?: AbortSignal): Promise<void>` — new.
- `export function setShowArchived(state: CharactersState, showArchived: boolean): void` — new.
- `export function applyCharacter(state: CharactersState, character: Character): void` — new.

- Caller-compile edits (out of Source-files scope): None — both modules are new and have no callers yet (`005`–`008` bind to them).

Notes for later steps and for the coder:

- The id parameter is named `characterId` (string) in all five id-addressed calls; `005`–`008` bind to that name and to `Character` / `CharactersState` as frozen here.
- **No shared-client import is frozen.** `apiGet` / `apiPost` / `apiPatch` are not imported yet, and neither are `runInAction` or `fetchCharacters` in `charactersState.ts`: `noUnusedLocals` fails the typecheck on an unused import while the bodies throw. The coder adds them when filling the bodies.
- Each stub body starts with `void <param>;` lines only because `noUnusedParameters` is on; they are placeholders the coder deletes, not behaviour.
- Neither module imports `@mantine/notifications` (D12) and neither contains `parseInt` or an `id`-named `: number` binding — `tests/conventions.test.ts` and `tests/ids-are-strings.test.ts` stay green.
- Gate after this step: `npm run typecheck` from `frontend/` — clean (both tsconfigs). `npm test` not run (verifier's gate); no npm dependency added or changed.


### Step 005 — frozen interface (2026-10-02)

- `frontend/src/shared/MarkdownEditor.tsx` — `export type MarkdownEditorProps = { label: string; value: string; onChange: (markdown: string) => void; readOnly?: boolean }` — new.
  `readOnly` omitted means false; the type carries no default, the implementation does.
- `frontend/src/shared/MarkdownEditor.tsx` — `export function MarkdownEditor(props: MarkdownEditorProps): React.JSX.Element` — new.
  Declared as `_props` while the body is a stub (`noUnusedParameters`); the coder renames to
  `props` when filling it. Body: `throw new Error("MarkdownEditor is not implemented")`.
  A named function export (the `IconButton` / `ConfirmModal` shape), not a default export —
  `007` / `008` import `{ MarkdownEditor }` and `vi.mock` that named export.
- The module's first statement is `import "@mantine/tiptap/styles.css";` — frozen here because it
  is interface-visible: a `vi.mock` of this module replaces it, and the package stylesheet adds
  no `.css` file under `src/`, so `tests/stylesheets.test.ts` stays green. No `.css` file was added.
- `frontend/package.json` — six packages added under `dependencies` — new. Exact installed ranges:
  `"@mantine/tiptap": "7.17.8"` (pinned exact, matching `@mantine/core` / `hooks` / `notifications`
  — its own peer range is `@mantine/core: 7.17.8`), `"@tiptap/react": "^2.27.3"`,
  `"@tiptap/pm": "^2.27.3"`, `"@tiptap/starter-kit": "^2.27.3"`,
  `"@tiptap/extension-link": "^2.27.3"`, `"tiptap-markdown": "^0.8.10"`.
  Resolved in `package-lock.json`: `@mantine/tiptap` 7.17.8, all four `@tiptap/*` 2.27.3
  (`@tiptap/core` 2.27.3 transitively), `tiptap-markdown` 0.8.10.
- `frontend/package-lock.json` — regenerated by `npm install <pkg>@<range> …` from `frontend/`,
  never hand-edited — changed.
- Caller-compile edits (out of Source-files scope): None. Nothing imports `MarkdownEditor` yet.

Notes for later steps: the install resolved with no `ERESOLVE` and no version compromise — the
constraints in `005.context.md` held exactly, so there is nothing to record in `## Notes & Issues`.
TipTap 2 is in place (`@tiptap/*` major 2 ranges), `@mantine/tiptap`'s major equals
`@mantine/core`'s (7), and `tiptap-markdown` is on the 0.8 line. The npm WARN EBADENGINE lines
during install are pre-existing (`jsdom@30.1.1` vs the local Node 24.11.0) and unrelated.
No `.js` / `.jsx` / `.mjs` / `.cjs` file exists under `frontend/` outside `node_modules/` and
`dist/`. Gate after this step: `npm run typecheck` from `frontend/` — clean (both tsconfigs).
`npm test` not run (verifier's gate); `npm run build` not run (optional at skeleton stage).


### Step 006 — frozen interface (2026-10-02)

`frontend/src/app/characterScreenState.ts` (new file). Every derivation and effect body
throws `new Error("not implemented: <name>")`; only the class's field declarations and the
constructor's initial state are real, because a data class's initial state *is* its shape
(and `strictPropertyInitialization` requires the two assignments).

- `export type CharacterScreenStatus = "loading" | "ready" | "not-found" | "failed"` — new.
- `export type CharacterSubmitStatus = "idle" | "submitting"` — new.
- `export class CharacterScreenState` — new. Observable fields only, in declaration order:
  `characterId: string | null` (as constructed; `null` = new mode), `status: CharacterScreenStatus`,
  `character: Character | null = null`, `name = ""`, `sheet = ""`,
  `submitStatus: CharacterSubmitStatus = "idle"`, `error: string | null = null`.
  Constructor: `constructor(characterId: string | null)` — assigns `this.characterId`, sets
  `this.status = characterId === null ? "ready" : "loading"`, then calls exactly
  `makeAutoObservable(this, {}, { autoBind: true })` (last, so both assigned fields are annotated).
  No methods, no computed getters.
- `export function isNewCharacter(state: CharacterScreenState): boolean` — new, pure.
- `export function isDirty(state: CharacterScreenState): boolean` — new, pure.
- `export function canSubmit(state: CharacterScreenState): boolean` — new, pure.
- `export async function loadCharacter(state: CharacterScreenState, signal?: AbortSignal): Promise<void>` — new.
- `export async function submitCreate(state: CharacterScreenState, characters: CharactersState, onCreated: (characterId: string) => void, signal?: AbortSignal): Promise<void>` — new.
  The third parameter is a **callback, not a router function** — the module stays React-free (`006.context.md`).
- `export async function submitSave(state: CharacterScreenState, characters: CharactersState, signal?: AbortSignal): Promise<void>` — new.
- `export async function submitArchive(state: CharacterScreenState, characters: CharactersState, signal?: AbortSignal): Promise<void>` — new.
- `export async function submitRestore(state: CharacterScreenState, characters: CharactersState, signal?: AbortSignal): Promise<void>` — new.
- Caller-compile edits (out of Source-files scope): None — the module is new and has no callers yet (`007` binds to it).

Notes for later steps and for the coder:

- The workspace-state parameter is named `characters` and is the frozen `CharactersState`
  from `004`; `Character`, `CharactersState` and `applyCharacter` are imported from `004`'s
  modules, never redeclared. `signal` is the last parameter of every effect.
- **Only three imports are frozen**: `makeAutoObservable` from `mobx`, `import type { Character }
  from "./charactersApi"` and `import type { CharactersState } from "./charactersState"`.
  `runInAction`, `applyCharacter`, the five `charactersApi` calls, `ApiError` / `isApiError` and
  the per-action error sentences are **not** imported or declared yet — `noUnusedLocals` /
  `noUnusedImports` fail the typecheck while the bodies throw (same constraint as `004`). The
  coder adds them when filling the bodies.
- Each stub body starts with `void <param>;` lines only because `noUnusedParameters` is on; they
  are placeholders the coder deletes, not behaviour.
- The module imports no `@mantine/notifications` (D12) and contains no `parseInt` and no
  `id`-named `: number` binding — `tests/conventions.test.ts` and `tests/ids-are-strings.test.ts`
  stay green.
- Gate after this step: `npm run typecheck` from `frontend/` — clean (both tsconfigs). `npm test`
  not run (verifier's gate); no npm dependency added or changed.


### Step 007 — frozen interface (2026-10-02)

`frontend/src/app/CharacterScreen.tsx` (new file) and a minimal edit to 008's
`frontend/src/app/App.tsx`. Both component bodies throw
`new Error("not implemented: <name>")`; the two props types and the `App.tsx` wiring are
the frozen contract.

- `frontend/src/app/CharacterScreen.tsx` — `export type CharacterScreenProps = { characters: CharactersState; characterId: string | null }` — new.
  `characters` is 004's frozen `CharactersState` (the one `App` instance, D11), imported as
  `import type { CharactersState } from "./charactersState"` and never redeclared.
  `characterId` is the `:id` parameter verbatim, `null` = new mode; nothing parses it.
- `frontend/src/app/CharacterScreen.tsx` — `export const CharacterScreen = observer(function CharacterScreen(props: CharacterScreenProps): React.JSX.Element { ... })` — new.
  The `observer(function Name(...))` + `React.JSX.Element` shape every component in this repo
  uses (`CreateUserModal`, `WorkspaceShell`). Declared `_props` while the body is a stub
  (`noUnusedParameters`); the coder renames to `props` when filling it.
- `frontend/src/app/CharacterScreen.tsx` — `export type CharacterRouteProps = { characters: CharactersState }` — new.
- `frontend/src/app/CharacterScreen.tsx` — `export function CharacterRoute(props: CharacterRouteProps): React.JSX.Element` — new.
  A plain function, **not** an `observer`: it reads no observable, only the `:id` param. Also
  `_props` while stubbed. Its body (the `useParams` read and the keyed `CharacterScreen`) is
  the coder's.
- `frontend/src/app/App.tsx` — `export function App(props: AppProps): React.JSX.Element` — **signature unchanged**; body changed in exactly three places:
  1. `const [characters] = useState(() => new CharactersState());` as the second statement
     (D11; `useState`, never `useMemo`);
  2. `<Route path="/characters/new" element={<CharacterScreen characters={characters} characterId={null} />} />`
     replacing `element={null}`;
  3. `<Route path="/characters/:id" element={<CharacterRoute characters={characters} />} />`
     replacing `element={null}`.
  New imports: `useState` from `react`, `{ CharacterRoute, CharacterScreen }` from
  `./CharacterScreen`, `{ CharactersState }` (value import) from `./charactersState`. The other
  five routes, the `*` "Page not found", the `WorkspaceShell` wrapper (still `user` / `storage` /
  `children`) and `AppProps` are untouched. One stale sentence in `App`'s doc comment ("in 008
  every declared route's element is empty") was corrected; no other prose changed.
- Caller-compile edits (out of Source-files scope): None. `WorkspaceShell.tsx` is deliberately
  untouched — step 008 passes `characters` to it.

Notes for the test-coder and the coder:

- **Only three imports are frozen** in `CharacterScreen.tsx`: `import type * as React from "react"`,
  `observer` from `mobx-react-lite`, and `import type { CharactersState } from "./charactersState"`.
  `useState` / `useEffect` / `useRef`, `useNavigate` / `useParams`, `runInAction`, the Mantine
  components, the Tabler icons (`IconPlus`, `IconDeviceFloppy`, `IconArchive`, `IconArchiveOff`),
  `MarkdownEditor`, `isArchived` and all of `characterScreenState`'s exports are **not** imported
  yet — `noUnusedLocals` fails the typecheck while the bodies throw (the same constraint as
  004/005/006). The coder adds them when filling the bodies.
- The module imports no `@mantine/notifications` (D12), adds no `.css` file, and contains no
  `parseInt` and no `id`-named `: number` binding — `tests/conventions.test.ts`,
  `tests/stylesheets.test.ts` and `tests/ids-are-strings.test.ts` stay green.
- 008's `tests/app/App.test.tsx` asserts an **empty** main region at `/characters/new` and
  `/characters/1`; with the stubs wired those two clauses now fail (the stub throws). That is
  expected and is the test-coder's DoD-13 amendment, not a skeleton defect.
- Gate after this step: `npm run typecheck` from `frontend/` — clean (both tsconfigs). `npm test`
  not run (verifier's gate); no npm dependency added or changed.


### Step 008 — frozen interface (2026-10-02)

`frontend/src/app/CharacterTree.tsx` (new file) and minimal edits to 008's
`frontend/src/app/WorkspaceShell.tsx` and `frontend/src/app/App.tsx`. The component body
throws `new Error("not implemented: CharacterTree")`; the props type and the two wirings
are the frozen contract.

- `frontend/src/app/CharacterTree.tsx` — `export type CharacterTreeProps = { characters: CharactersState }` — new.
  The single prop is 004's frozen `CharactersState` — the one instance `App` creates (D11),
  imported as `import type { CharactersState } from "./charactersState"` and never redeclared.
  No `characterId` prop and no router prop: the current character is read from the location
  inside the component.
- `frontend/src/app/CharacterTree.tsx` — `export const CharacterTree = observer(function CharacterTree(props: CharacterTreeProps): React.JSX.Element { ... })` — new.
  The `observer(function Name(...))` + `React.JSX.Element` shape used by `WorkspaceShell` and
  `CharacterScreen`. Declared `_props` while the body is a stub (`noUnusedParameters`); the
  coder renames to `props` when filling it.
- `frontend/src/app/WorkspaceShell.tsx` — `WorkspaceShellProps` gains one **required** field,
  `characters: CharactersState` — changed (was `{ user: CurrentUser; storage: LayoutStorage | null; children: React.ReactNode }`).
  Declared between `storage` and `children`. `WorkspaceShell`'s own signature
  (`observer(function WorkspaceShell(props: WorkspaceShellProps): React.JSX.Element)`) is
  unchanged; the destructure becomes `const { user, storage, characters, children } = props;`.
- `frontend/src/app/WorkspaceShell.tsx` — the expanded column's empty body is now the tree's
  mount — changed. `<Box flex={1} />` became
  `<Box flex={1}><CharacterTree characters={characters} /></Box>`, still between the
  "Collapse tree" `Group` and the `UserMenu` footer, still inside the `nav` column (the
  `.app` grid keeps exactly two children). The rail branch, the overlay effects, the collapse
  persistence, `shellClassName`, the "Workspace navigation" label and `COLUMN_BG` /
  `SEARCH_PATH` / `NEW_CHARACTER_PATH` are untouched; only the body comment was updated.
  New imports: `{ CharacterTree }` from `./CharacterTree`,
  `import type { CharactersState } from "./charactersState"`.
- `frontend/src/app/App.tsx` — `export function App(props: AppProps): React.JSX.Element` —
  **signature unchanged**; body changed in exactly one place: the `WorkspaceShell` element is
  now `<WorkspaceShell user={user} storage={storage} characters={characters}>`, passing the
  `CharactersState` 007 already created with `useState`. No new import, no new statement, no
  route change.
- Caller-compile edits (out of Source-files scope): None. `src/app/App.tsx` is the only
  `WorkspaceShell` call site in `src/` (verified by grep; `AppBoot.tsx` renders `App`, not the
  shell), and it is a Source file of this step.

Notes for the test-coder and the coder:

- **Only three imports are frozen** in `CharacterTree.tsx`: `import type * as React from "react"`,
  `observer` from `mobx-react-lite`, and `import type { CharactersState } from "./charactersState"`.
  `useEffect`, `useMatch` / `useLocation` / `Link`, the Mantine components (`Group`, `Stack`,
  `Switch`, `Loader`, `Text`, `Button`, `NavLink`, `Badge`), `IconButton`, `IconSearch` /
  `IconPlus`, and `loadCharacters` / `setShowArchived` / `isArchived` are **not** imported yet —
  `noUnusedLocals` fails the typecheck while the body throws (the same constraint as 004–007).
  The coder adds them when filling the body.
- The component sits **outside** `<Routes>`, so `useParams` would not see `:id`; nothing in the
  frozen signature assumes it. The current id is the coder's `useMatch("/characters/:id")` read,
  and `/characters/new` must match no row.
- The module imports no `@mantine/notifications` (D12), adds no `.css` file, and contains no
  `parseInt` and no `id`-named `: number` binding — `tests/conventions.test.ts`,
  `tests/stylesheets.test.ts` and `tests/ids-are-strings.test.ts` stay green.
- **Known test-side typecheck break, by design (DoD-7/DoD-11, test-coder's work):**
  `tests/app/WorkspaceShell.test.tsx(124,10)` — `renderShell` omits the new required
  `characters` prop (TS2741). It is the only error in the whole project; `src` alone and
  `tsconfig.node.json` both compile clean.
- Gate after this step: `tsc --noEmit` over `src` — clean; `tsc --noEmit -p tsconfig.node.json`
  — clean; the full `npm run typecheck` reports exactly the one test-file error above.
  `npm test` not run (verifier's gate); no npm dependency added or changed.


## Tests

### Step 001 — tests (2026-10-02)

- `backend/tests/test_db_schema.py` (009 delta appended) — covers DoD-1, DoD-2, DoD-3, DoD-4 —
  `characters` is registered and is 009's only table; its exactly-seven columns, `id` primary
  key, nullability and the absence of `model_ref` / `system_prompt` / `tools` / `rp_language` /
  `preferred_language`; the `users.id` foreign key and the non-unique `user_id` index;
  `create_all` on a fresh engine creating `characters` with the FK enforced under
  `PRAGMA foreign_keys = ON`.
- `backend/tests/test_db_schema.py` (006's two assertions rescoped, names unchanged) — covers
  DoD-11 — `test_registry_gains_exactly_the_two_new_tables__S006_001_DoD5` and
  `test_create_all_on_a_fresh_file_database_creates_both_tables__S006_001_DoD5` now subtract the
  new `LATER_THAN_006_TABLES = {"characters"}` set and additionally assert `PRE_006_TABLES` is
  still present, so they keep failing if a 006 or pre-006 table disappears. The already-safe
  subset check in `test_every_registry_table_uses_the_one_shared_metadata__S006_001_DoD7` is
  untouched. **Shared delta shape** (used for DoD-1 too, and for `010`+): a feature's delta is
  `set(tables) - PRE_<n>_TABLES - LATER_THAN_<n>_TABLES == NEW_<n>_TABLES`; a feature that adds a
  table appends it to every earlier feature's `LATER_THAN_*` set and declares its own.
  `LATER_THAN_009_TABLES` is seeded empty for `010`.
- `backend/tests/test_characters_models.py` (new) — covers DoD-5, DoD-6, DoD-7, DoD-8, DoD-9 —
  `CharacterNotFoundError` as a 404 `DomainError` with code `character_not_found`, empty
  `detail`, and the rendered envelope from a route on an app with the handlers registered;
  `CharacterResponse`'s decimal-string `id`, `null` `archived_at` and exactly the six wire keys;
  `CharacterListResponse`'s single `characters` key and row order; D8's strip-then-non-empty
  `name`, the `""` `sheet` default, verbatim `sheet` and ignored unknown keys on both request
  models, and D7's absent-or-`null` on the update model.
- `backend/tests/test_admin_db_router.py` — covers DoD-12 — `UNDECLARED_NAMES[0]` is now
  `"setups"` (feature `010`'s, still undeclared) instead of `"characters"`; no other entry and no
  assertion in that file changed.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 [manual/live, no test], DoD-11 ✓, DoD-12 ✓.

### Step 002 — tests (2026-10-02)

- `backend/tests/test_characters_service.py` (new) — covers DoD-1 … DoD-11 — the six
  owner-scoped operations against a per-test file database. File-local `engine` fixture
  (`schema.metadata.create_all` over `db_engine`) seeding **two** users (`101`, `202`) with a
  local `_insert_user`, one connection per service call via `engine.connect()` (writes too),
  a per-test real `SnowflakeGenerator(node_id=1)` and a local `_FixedIdGenerator` where a
  known id matters. No shared fixture added (`conftest.py` untouched).
  - DoD-1 — create returns the minted id, the given name/sheet, `archived_at` `None`,
    `created_at == updated_at`, both matching `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$`.
  - DoD-2 — `get_character` answers an equal value and the listing contains it.
  - DoD-3 — two owners, each with a working and an archived character; each listing carries
    only its owner's ids, with and without `include_archived`.
  - DoD-4 — three characters created in sequence, the middle one archived: default listing is
    `[third, first]`, include-archived listing is `[third, second, first]` (D10).
  - DoD-5 — parametrized over get / update / archive / restore: another user's id raises
    `CharacterNotFoundError` and leaves the owner's name, sheet, `archived_at` and `updated_at`
    unchanged; an id belonging to nobody raises the same error.
  - DoD-6 — name-only, sheet-only and both-fields updates (other field kept, `created_at`
    unchanged, `updated_at` not earlier, visible through a later `get_character`); neither
    field returns the current row with `updated_at` unchanged (D7).
  - DoD-7 — archive stamps a fixed-width `archived_at`, drops out of the default listing,
    stays in the include-archived listing and stays readable by id; a second archive returns
    the same `archived_at` **and** the same `updated_at` (D9).
  - DoD-8 — restore clears `archived_at` and the row returns to the default listing; restoring
    a working character returns it unchanged (same `updated_at`).
  - DoD-9 — updating an archived character succeeds and leaves `archived_at` as stamped.
  - DoD-10 — after `list_characters` and after `get_character`, `connection.begin()` on the
    same connection succeeds (two tests).
  - DoD-11 — `inspect.getsource` over `app.services.characters`: no `delete(` substring, no
    `DELETE` SQL keyword (`\bdelete\b`, case-insensitive) and no `fastapi` import line.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓.

### Step 003 — tests (2026-10-02)

- `backend/tests/test_characters_router.py` (new) — covers DoD-1 … DoD-13 — the six wire-contract
  routes exercised end to end over HTTP against the real `create_app()` factory, pinned to the
  per-test database through `dependency_overrides[get_settings]`. File-local fixtures only
  (`conftest.py` untouched): `engine` (`schema.metadata.create_all` over `db_engine`) seeding
  **three** accounts — roleplayers A (`9100001` `aster`) and B (`9100002` `briar`) and an
  administrator (`9100003` `founder`) — a local `_insert_user` with the `TIMESTAMP` constant and the
  real `hash_password`, and an `application` fixture. **No shared `client` fixture:** `_as()` builds
  a fresh `TestClient` per caller carrying exactly that account's session cookie read from
  `POST /api/auth/login`'s `Set-Cookie`, so cookies never leak between A, B and the administrator.
  Every assertion is on the HTTP response; no handler name is bound.
  - DoD-1 — parametrized over all six routes (GET/POST `""`, GET/PATCH `/{id}`, POST
    `/{id}/archive|restore`): with no cookie each answers 401 with envelope code
    `not_authenticated` (D6). POST/PATCH send a *valid* body so only the guard can fail.
  - DoD-2 — three tests: the 201 body has exactly the six wire keys, `name` "Aria", `sheet`
    "# Aria", `archived_at` null and both timestamps in the fixed-width form; `id` is a JSON
    **string** of decimal digits (`isinstance(..., str)` plus the quoted form in `response.text`);
    a following `GET /api/characters` contains that row.
  - DoD-3 — parametrized over `name` `""`, `"   "` and absent: each answers **422** and the
    listing is identical to the one taken before (D8, native validation). A separate test
    asserts `"  Aria "` is answered and read back as `"Aria"`.
  - DoD-4 — A and B each with one working and one archived character: each listing, with and
    without `include_archived=true`, carries only its own owner's ids (R5).
  - DoD-5 — three parametrized tests over GET / PATCH / archive / restore on A's id as B:
    (a) 404 with code `character_not_found` and `detail == {}`; (b) A reads its character back
    unchanged (full body equality); (c) the body for B's request **equals** the body for
    `UNKNOWN_ID` (an id that exists for nobody) — the no-existence-leak assertion of D8.
  - DoD-6 — PATCH `{"name": "Bo"}` then `{"sheet": "new body"}`, each answering the updated row
    with the other field preserved, and a following `GET /{id}` returning both (D7).
  - DoD-7 — archive answers 200 with a fixed-width `archived_at` string; the default listing
    omits the id, `include_archived=true` includes it, and `GET /{id}` still answers 200 (R6).
  - DoD-8 — restore answers 200 with `archived_at` null and the default listing contains it again.
  - DoD-9 — two tests: `DELETE /api/characters/{id}` and `DELETE /api/characters` each answer
    **405** (status only, no body asserted — Starlette answers it, not our code), and
    `GET /{id}` afterwards still returns the character unchanged.
  - DoD-10 — a second archive answers 200 with the **same** `archived_at` as the first, and the
    read-back agrees (D9).
  - DoD-11 — the seeded administrator creates a character, sees it in its own listing, does not
    see the roleplayer's, and the roleplayer does not see the administrator's (D6).
  - DoD-12 — parametrized over `/api/characters/abc` (GET) and `/api/characters/abc/archive`
    (POST), signed in: each answers **422** (`SnowflakeIn`).
  - DoD-13 — two tests: a create and a PATCH carrying `user_id` (B's id) and `archived_at` are
    accepted with those keys ignored — the row stays `archived_at` null, appears in the caller's
    listing, is absent from B's include-archived listing and answers 404 to B (D8).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 [manual/live, no test].

### Step 004 — tests (2026-10-02)

Both files new, under `frontend/tests/app/`, Vitest with `globals: false` (every helper
imported explicitly from `"vitest"`). `fetch` is stubbed per test with `vi.stubGlobal` over a
local `stubFetch` helper, `afterEach` does `vi.unstubAllGlobals(); vi.restoreAllMocks();`, and
no network-mocking library is used. Every `it` title ends `— DoD-N`. Requests are read back as
`{ method, path, search }` plus the parsed JSON body, so a URL and a body are pinned exactly.
Every character id in both files is a decimal string past `Number.MAX_SAFE_INTEGER`
(`72500000000000000{1..6}`), and the fixtures' ids **ascend while their `created_at` descends**,
so any ordering derived from an id fails.

- `frontend/tests/app/charactersApi.test.ts` (new) — covers DoD-1, DoD-2, DoD-3, DoD-4 — the six
  wire-contract calls over a stubbed `fetch`.
  - DoD-1 — five tests: `fetchCharacters(false)` makes exactly one call,
    `GET /api/characters` with `search === ""`; `fetchCharacters(true)` exactly
    `GET /api/characters?include_archived=true`; the resolved value is the payload's
    `characters` array unwrapped and in the payload's order; an empty listing resolves `[]`;
    the ids come back as the identical strings (`typeof` `"string"`, equal to the big literal).
  - DoD-2 — nine tests: `fetchCharacter("7250000000000000001")` →
    `GET /api/characters/7250000000000000001`; `createCharacter` → `POST /api/characters` with a
    body whose keys are exactly `name`, `sheet`; `updateCharacter` → `PATCH /api/characters/<id>`
    with `Object.keys(body)` exactly `["name"]`, exactly `["sheet"]` and both when both are
    given, and no keys for an empty patch (a body of `{}` or no body both pass);
    `archiveCharacter` / `restoreCharacter` → `POST /api/characters/<id>/archive` / `/restore`.
    Each asserts the resolved value equals the response's character. A final loop re-asserts the
    big id appears verbatim in the path of all four id-addressed routes.
  - DoD-3 — two tests: a 404 `{ error: { code: "character_not_found", … } }` envelope makes
    `fetchCharacter` reject with a value `isApiError` accepts, `.code === "character_not_found"`
    and `.status === 404`; the same envelope rejects `updateCharacter` / `archiveCharacter` /
    `restoreCharacter` identically (the Interface intent's "rethrown unchanged").
  - DoD-4 — two tests: `isArchived` is `true` for a character whose `archived_at` is a string and
    `false` when it is `null`.
- `frontend/tests/app/charactersState.test.ts` (new) — covers DoD-5 … DoD-11 — `CharactersState`,
  `loadCharacters`, `setShowArchived`, `applyCharacter`. Helpers: `deferred<Response>()` to hold a
  response open, `flush()`, `withCharacters(rows, showArchived?)` seeding a ready state through
  `runInAction`, `snapshot()` over `toJS`.
  - DoD-5 — six tests: with a held-open response `status` is `"loading"` while the request is
    pending and `"ready"` after it resolves — asserted both from a fresh `"idle"` state **and
    from an already-`"ready"` state** (the step file's unconditional `"loading"`, unlike
    `usersPageState.loadUsers`'s guard); a successful load writes exactly the server's rows in the
    server's order (including an order that is *not* `created_at`-descending); an empty listing is
    `"ready"` with no rows; the request carries no query while `showArchived` is false and
    `?include_archived=true` after `setShowArchived(state, true)`.
  - DoD-6 — five tests: a 500 envelope and a transport rejection each leave `status` `"failed"`
    with the previous rows intact and the promise resolving `undefined`; the same from a fresh
    state leaves `characters` `[]`; with a signal aborted mid-flight (the fetch stub rejecting on
    `abort`) and with a response resolving *after* the abort, the state equals the snapshot taken
    at the moment of the abort — nothing written.
  - DoD-7 — three tests: applying a row whose id is present replaces it at the **same index** with
    the new values and leaves the neighbours and the length alone (middle row, first row, and with
    `showArchived` true).
  - DoD-8 — three tests: a now-archived row is removed while `showArchived` is false; it is
    replaced in place and kept while `showArchived` is true; a restored row replaces its archived
    self in place.
  - DoD-9 — five tests: an absent row newer than all lands first; one whose `created_at` falls
    between two lands between them; one older than all lands last (`004.context.md`'s "or at the
    end"); the first row of an empty list is inserted; an absent archived row is inserted by
    `created_at` while `showArchived` is true ("visible" = working, or archived with the flag on).
  - DoD-10 — three tests: an absent archived row while `showArchived` is false leaves
    `characters` unchanged — including one newer than every row, and against an empty list.
  - DoD-11 — nine tests: `setShowArchived` sets the flag both ways and the `fetch` stub is never
    called, and it leaves rows and status alone; an `autorun` reading `state.characters` re-runs
    after `applyCharacter` (both an insert and an in-place replacement) and one reading
    `state.showArchived` re-runs after `setShowArchived`, each asserting the value seen on the
    last run; the reflection checks `usersPageState.test.ts` uses —
    `Object.getOwnPropertyNames(CharactersState.prototype)` equals `["constructor"]`, the
    observable fields are exactly `characters`, `showArchived`, `status` and none is
    `isComputedProp`, no own property is a function or computed; a fresh state is
    `{ characters: [], status: "idle", showArchived: false }`; the three operations are free
    functions and the prototype carries no `loadCharacters`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓. (All eleven are `[test]`; none is `[manual/live]`.)

### Step 005 — tests (2026-10-02)

One new file, `frontend/tests/shared/MarkdownEditor.test.tsx`, bound to the frozen
`MarkdownEditorProps` / named `MarkdownEditor` export. Vitest with `globals: false`
(everything imported from `"vitest"`), the component rendered inside
`shared/AppProviders`, every `it` title ending `— DoD-N`. Because `useEditor` can return
`null` on the first render, every test's first assertion is a `findBy…` / `waitFor`. The
editable surface is recognised as the element with role `textbox` named "Persona", and all
content queries are scoped `within` it. A `settle()` helper (`act` + a macrotask) is used
before asserting that `onChange` was *not* called.

- `frontend/tests/shared/MarkdownEditor.test.tsx` (new) — covers DoD-1, DoD-2, DoD-3,
  DoD-4, DoD-5.
  - DoD-1 — one test: rendered with `label` "Persona", a textbox with accessible name
    "Persona" is exposed.
  - DoD-2 — three tests over one markdown value (a level-2 heading "Voice", a paragraph
    with `**bold**`, a two-item bullet list): a level-2 heading named "Voice" inside the
    surface; a `strong` element whose text is "bold"; exactly two list items, reading
    "first item" and "second item".
  - DoD-3 — three tests: `onChange` is not called on mount; it is still not called after a
    re-render with a different `value`; after that re-render the new heading and body text
    are shown and the old heading and body text are gone.
  - DoD-4 — five tests: with `readOnly` true no button renders at all and the textbox is
    `contenteditable="false"`; with `readOnly` false formatting buttons render and the
    textbox is `contenteditable="true"`; re-rendering false → true removes every button and
    leaves the surface `contenteditable="false"`.
  - DoD-5 — nine tests over `frontend/package.json` and the `frontend/` tree (config, not
    implementation): each of the six packages is listed under `dependencies` (one `it.each`
    case per package); `@mantine/tiptap`'s major equals `@mantine/core`'s; every
    `@tiptap/*` range is on major 2; no `.js` / `.mjs` / `.cjs` file exists anywhere under
    `frontend/` outside the generated directories (`node_modules/`, `dist/`, `coverage/`).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 [manual/live, no test],
  DoD-7 [manual/live, no test].
- Left to `[manual/live]` deliberately: **real typing and toolbar clicks producing
  markdown through `onChange`** (round-tripping `**bold**` / `## …`) — DoD-6 — and the
  **build with the new dependencies plus the toolbar's styling** — DoD-7. Per `context.md`
  "TipTap in jsdom" and `005.context.md`, jsdom has no layout and only partial
  `contenteditable`/selection support, so driving the ProseMirror surface through
  `user-event` is unreliable; the optional DOM-mutation-driven `onChange` check was
  omitted rather than risk a flaky test.
- Guard-test rescope (2026-10-02, red-gate TEST fault repair): `frontend/tests/build-config.test.ts`
  — the clause "declares none of the deferred packages, @mantine/form, or any linter (DoD-8)"
  (an earlier feature's DoD) recorded the six TipTap packages as *deferred*; step 005 is the
  feature that un-defers them (D3), so the `@tiptap/*`, `tiptap-markdown` and `@mantine/tiptap`
  entries were removed from that clause's forbidden list. `@mantine/form`, every linter,
  `react-markdown` and `@dnd-kit/*` remain forbidden; the test name and `(DoD-8)` tag are
  unchanged. This file is **outside step 005's declared Test files** — the edit was explicitly
  authorized by the orchestrator, on the precedent of step 001's DoD-11/DoD-12 backend guard
  rescopes.

### Step 006 — tests (2026-10-02)

One new file, `frontend/tests/app/characterScreenState.test.ts`, bound to the frozen
`CharacterScreenState(characterId)` / `isNewCharacter` / `isDirty` / `canSubmit` /
`loadCharacter` / `submitCreate` / `submitSave` / `submitArchive` / `submitRestore`
signatures. Vitest with `globals: false`, `fetch` stubbed per test with `vi.stubGlobal`
over a URL-routed in-memory backend (`stubBackend` records `{ method, path, search, body }`
per request), `deferred<Response>()` to hold a response open, `flush()`, and
`afterEach` doing `vi.unstubAllGlobals(); vi.restoreAllMocks();`. The id is a decimal
string past `Number.MAX_SAFE_INTEGER`. The four error sentences are file-level constants
compared with `toBe`. Every `it` title ends `— DoD-N`.

- `frontend/tests/app/characterScreenState.test.ts` (new) — covers DoD-1 … DoD-11.
  - DoD-1 — seven tests: a `null` state is new mode, `"ready"`, no character, empty draft,
    `"idle"`, no error (full snapshot); an id state is not new mode and starts `"loading"`;
    `canSubmit` false on an empty name and on three whitespace-only names, true on
    `"Aria Vance"` and on `"  Aria  "`; the reflection checks — the prototype is exactly
    `["constructor"]`, the observable fields are exactly `character`, `characterId`,
    `error`, `name`, `sheet`, `status`, `submitStatus`, none computed, no own property a
    function; the eight derivations/effects are free functions and the prototype carries no
    `submitSave`.
  - DoD-2 — four tests: exactly one `POST /api/characters` whose body keys are exactly
    `name`, `sheet` with the draft's values; `onCreated` called **once** with the response's
    id string (`typeof` `"string"`); the created row present in the workspace
    `CharactersState` and equal to the response; `submitStatus` `"submitting"` while the
    response is held open and `"idle"` after it.
  - DoD-3 — three tests (a 500 envelope, a native FastAPI 422, a transport rejection):
    `error` is exactly "Could not create the character.", `onCreated` never called, the
    workspace rows byte-identical to the snapshot taken before, `submitStatus` `"idle"`, and
    the promise resolving `undefined`.
  - DoD-4 — seven tests: success is `"ready"` with `character` equal to the response and the
    draft `name`/`sheet` copied from it, over exactly `GET /api/characters/<id>`; a 404
    `character_not_found` envelope is `"not-found"`; a 500 envelope and a transport failure
    are each `"failed"`; a retry from a `"failed"` state shows `"loading"` while pending;
    with the signal aborted mid-flight (abort-rejecting stub) and with a response resolving
    *after* the abort, the full state snapshot equals the one taken at the abort.
  - DoD-5 — six tests, each from a real successful load: `isDirty` and `canSubmit` both
    false immediately after; changing the draft `name` and changing the draft `sheet` each
    make both true; a whitespace-only draft name makes `canSubmit` false; `canSubmit` is
    false while `submitStatus` is `"submitting"` and true again at `"idle"`; a new-mode draft
    with a name is likewise blocked while submitting.
  - DoD-6 — one test with a held-open PATCH: the request is `PATCH /api/characters/<id>`
    with body keys exactly `name`, `sheet` and the name sent **as typed** (`"  Bo  "`);
    **before** the response `character` and the workspace row are still the previously
    loaded value (never optimistic); after it `character` equals the response, the draft
    name is the server-trimmed `"Bo"`, the draft sheet is the response's, `isDirty` is false
    and the workspace holds the updated row.
  - DoD-7 — three tests (500, native 422, transport): `error` is exactly "Could not save the
    character.", the edited draft `name`/`sheet` survive, `character` and the workspace rows
    are unchanged.
  - DoD-8 — one test: exactly one `POST /api/characters/<id>/archive`; `character` equals the
    response and its `archived_at` is the response's; the draft's unsaved name and sheet
    edits are unchanged; with `showArchived` false the workspace no longer lists the row
    (only the untouched neighbour remains).
  - DoD-9 — one test: exactly one `POST /api/characters/<id>/restore`; `character.archived_at`
    is null and equals the response; the workspace lists the row again, equal to the response.
  - DoD-10 — five tests: archive and restore each over a 500 envelope and a native 422, plus
    a transport failure for both — "Could not archive the character." / "Could not restore
    the character." exactly, `character` unchanged, workspace rows unchanged.
  - DoD-11 — three tests, each asserting the error is **already null while the second request
    is in flight** (`calls` has length 2 and `error` is null before the held-open response is
    resolved): save after a failed save, create after a failed create, and archive after a
    failed save (the second call's path asserted as the archive route).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓. (All eleven are `[test]`; none is `[manual/live]`.)

### Step 007 — tests (2026-10-02)

- `frontend/tests/app/CharacterScreen.test.tsx` (new) — covers DoD-1 … DoD-12 — the screen's
  rendered behaviour at both routes, bound to the frozen `CharacterScreen`
  (`characters` / `characterId`) and `CharacterRoute` (`characters`). Harness: the two routes
  inside a `<main>` landmark (the centre column the shell gives them) in a `MemoryRouter`
  inside `AppProviders`, one `CharactersState` per render (D11), a location/navigation probe
  (`probe navigate` / `probe back`) beside the routes, `userEvent.setup({ pointerEventsCheck: 0 })`,
  a URL-routed `fetch` stub recording every request, and the sanctioned `vi.mock` of
  `src/shared/MarkdownEditor` (a labelled `<textarea>` honouring `label` / `value` /
  `onChange` / `readOnly`). Loader = `.mantine-Loader-root`, notification =
  `.mantine-Notification-root`; everything else is queried by role + accessible name or text.
  - DoD-1 — at `/characters/new`: heading "New character", textboxes "Name" and "Persona", a
    **disabled** "Create", no "Archive" button, no "Sessions" heading.
  - DoD-2 — typing a name enables "Create" and the `fetch` stub records **zero** calls.
  - DoD-3 — two tests: typing name + persona and pressing "Create" issues exactly one
    `POST /api/characters` whose body carries that name and sheet, the probe's location
    becomes `/characters/9007199254740993` (the response's id verbatim, past
    `Number.MAX_SAFE_INTEGER`) and `documentNavigation.assign` is never called; and, per D1's
    `replace`, pressing the probe's back control afterwards leaves the location on the new id
    rather than returning to `/characters/new`.
  - DoD-4 — a 500 on the create: "Could not create the character." renders in the screen, the
    location stays `/characters/new`, the Name field still holds the typed name, and no
    `.mantine-Notification-root` exists (D12).
  - DoD-5 — a held-open GET shows a Loader; on the resolved 200 the loader is gone and the
    screen shows a heading with the character's name, "Name" holding it, "Persona" holding its
    sheet, a **disabled** "Save", an "Archive" button, no "Archived" text, a "Sessions" heading.
  - DoD-6 — editing both fields enables "Save"; pressing it issues exactly one
    `PATCH /api/characters/<id>` carrying both `name` and `sheet`; after the response the
    heading shows the **server's** name and "Save" is disabled again.
  - DoD-7 — "Archive" POSTs `…/archive` once; afterwards "Archived" and "Restore" are shown
    and "Archive" is gone; "Restore" then POSTs `…/restore` once and afterwards "Archived" is
    gone and "Archive" is back.
  - DoD-8 — a character loaded with `archived_at` set shows "Archived" and "Restore" (no
    "Archive"), both textboxes are enabled, typing changes both values and "Save" becomes
    enabled (D4, D9).
  - DoD-9 — a 404 `character_not_found`: "Character not found" inside the `main` region, no
    "Retry" button, no notification.
  - DoD-10 — three tests: a 500 and a transport rejection each render "Could not load the
    character" **and** "Retry"; pressing "Retry" makes the GET count for that id go 1 → 2 and,
    on the success, the heading and the "Name" field show the character and the failure text
    is gone.
  - DoD-11 — a failed Save: "Could not save the character." renders and the edited name and
    persona are still in the fields.
  - DoD-12 — from `/characters/<a>` with an unsaved draft name, navigating in-entry to
    `/characters/<b>` requests `b` exactly once and shows `b`'s name in the heading, the "Name"
    field and the "Persona" field, with the draft value nowhere in the document.
- `frontend/tests/app/App.test.tsx` (amended — 009 step 007 owns only DoD-13) — covers DoD-13.
  **Replaced:** `DECLARED_ROUTES` (six paths) became `EMPTY_CENTRE_ROUTES`
  (`/`, `/sessions/1`, `/settings`, `/search`), so 008's two `it.each` clauses
  "renders the shell at %s — DoD-10" and "renders no centre content at %s — DoD-10" no longer
  run for `/characters/new` and `/characters/1` — those two paths' empty-centre assertions are
  gone. **Kept unchanged:** both `it.each` clauses for the other four routes and the
  undeclared-path clause "renders the shell with Page not found inside the main region —
  DoD-11". **Added:** a describe block with two DoD-13 clauses — at `/characters/new` the
  shell's "Workspace navigation" is present and the main region holds the "New character"
  heading, the "Name" and "Persona" textboxes and a "Create" button; at `/characters/1`, with
  `GET /api/characters/1` stubbed, the nav is present and the main region holds that
  character's heading, name and sheet. The file now also mocks `src/shared/MarkdownEditor`
  with the sanctioned stub and stubs `fetch` per test (`afterEach` unstubs). No other 008
  assertion changed — step 008 handles the tree's effect on this file.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 [manual/live, no test].

### Step 008 — tests (2026-10-02)

- `frontend/tests/app/CharacterTree.test.tsx` (new) — covers DoD-1, DoD-2, DoD-3, DoD-4,
  DoD-5, DoD-6 — the tree rendered alone under a `MemoryRouter` (it sits outside `<Routes>`),
  inside a `tree-host` wrapper so "the tree's controls" is a scope, with a `CharactersState`
  prop, a URL-routed `fetch` recording every request, a location probe and a
  `documentNavigation.assign` spy.
  - DoD-1 — three tests: the mount issues exactly one request, `GET /api/characters` with no
    query string (and no other request at all), and the "Characters" list holds one link per
    character with the payload's text in the payload's order (deliberately neither
    alphabetical nor id-ordered); each link's `href` is `/characters/<id>` with both ids past
    `Number.MAX_SAFE_INTEGER` carried verbatim; an empty payload renders no rows.
  - DoD-2 — three tests: clicking a row moves the probe to `/characters/<id>` and
    `documentNavigation.assign` is never called; rendered at `/characters/<id>` that row has
    `aria-current="page"` and the other row's `aria-current` is not `"page"`; at
    `/characters/new` no row is current.
  - DoD-3 — "Search" moves the router to `/search` and "New character" to `/characters/new`,
    each with no document navigation.
  - DoD-4 — three tests: on a fresh mount the switch is unchecked and the only request's
    search string is empty, with the archived row absent; turning it on makes the second
    request `GET /api/characters?include_archived=true` and the archived row carries the
    "Archived" badge while the working row does not; turning it off makes the third request
    the plain listing, leaves the switch unchecked and drops the archived row.
  - DoD-5 — three tests: a 500 and a transport rejection each render "Could not load
    characters" plus "Retry" inside the tree with no `.mantine-Notification-root`; "Retry"
    takes the listing count 1 → 2 and renders the rows, the failure text gone.
  - DoD-6 — three tests: in the ready state the tree's `button`-role elements are exactly
    "Search" and "New character"; there is exactly one switch/checkbox ("Show archived"), no
    textbox, and every row is a link; no row block contains a button and the tree has no
    control named /expand|collapse/.
- `frontend/tests/app/WorkspaceShell.test.tsx` (amended) — covers DoD-7. **Amendments:** the
  one `renderShell` helper now passes `characters={new CharactersState()}` (the new required
  prop); a `beforeEach` installs a URL-routed `fetch` answering `GET /api/characters` with one
  row and rejecting anything else; a `flush` helper lets the listing settle; `expectRail` and
  `expectExpandedColumn` now look their controls up **within the nav element** (the rail and
  the expanded column are exclusive branches of the same nav, and both may now offer
  "Search" / "New character"), with their assertions otherwise identical; new helpers
  `queryArchivedSwitch` / `queryCharactersList`. **Added** (nothing was replaced — the file
  carried no clause asserting Search / New character are absent from the expanded column): a
  describe block with two DoD-7 clauses — expanded, the nav holds "Collapse tree", the "Show
  archived" switch, the "Characters" list and the "User menu" trigger; after "Collapse tree"
  the rail shows "Search", "New character", "Expand tree" and "User menu" and holds neither
  the switch nor the list. 008's persistence, narrow-overlay and two-grid-children clauses are
  untouched and still hold.
- `frontend/tests/app/App.test.tsx` (amended) — covers DoD-8, DoD-9, DoD-10. **Amendments to
  existing clauses (stubs only, no assertion changed):** the four empty-centre `it.each`
  clauses and the undeclared-path clause now stub the characters backend and `await flush()`;
  007's `/characters/new` clause answers `GET /api/characters` (and rejects anything else) and
  007's `/characters/1` clause answers the listing alongside the item; `renderApp` now also
  renders a location probe. **Added:** `stubWorkspace`, an in-memory `/api/characters` backend
  (listing with the include-archived flag, create, read, patch, archive, restore) recording
  every request, plus nav-scoped tree queries, and three clauses —
  - DoD-8 — at `/characters/new`, typing "Aria" and pressing "Create" lands the probe on
    `/characters/<created id>` (an id past `Number.MAX_SAFE_INTEGER`), the tree shows an
    "Aria" row with `aria-current="page"`, and **no** `GET /api/characters` appears after the
    POST (the total listing count stays 1).
  - DoD-9 — at `/characters/<id>`, "Archive" removes the row from the tree; turning "Show
    archived" on brings it back with the "Archived" badge; "Restore" removes the badge; after
    turning the switch off the row is still there.
  - DoD-10 — at `/characters/<id>`, replacing the name and pressing "Save" makes the tree show
    the new name and no longer the old one.
- `frontend/tests/app/AppBoot.test.tsx` (amended — DoD-11, stubs only) — `stubSequence` is now
  routed by URL and answers `GET /api/characters` with `{ "characters": [] }` (it previously
  returned a never-settling promise for any non-`/api/me` path), and the two DoD-5 clauses
  that used `stubFetch(answerIdentity(role))` (which answered the identity body to **every**
  URL) now use `stubSequence([answerIdentity(role)])`. No boot-outcome assertion changed.
- `frontend/tests/entries.test.tsx` (amended — DoD-11, stubs only) — `stubAppIdentity` answers
  `GET /api/characters` with `{ "characters": [] }` before its "unexpected request in app
  entry test" rejection. No entry assertion changed.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓ (stub amendments in both files, cited in their comments; the files' own
  008 assertions are the test), DoD-12 [manual/live, no test].

## Notes & Issues

- Step 005: `editor.setEditable(editable)` defaults its second argument `emitUpdate` to
  **true** in TipTap 2, which would emit an `update` and make `onChange` fire on mount and
  on every `readOnly` change. It is called as `setEditable(!readOnly, false)`.

## Ultra phase

- orient: done 2026-10-01
- harvest: done — docs/.cache/ultra/009.characters/harvest.md (4 reports)
- skeleton: done — steps 001, 002, 003, 004, 005, 006, 007, 008
- tests: done — steps 001, 002, 003, 004, 005, 006, 007, 008
- red-gate: PASS (run 2) — run 1 FAILed on 003 (stray markup in its test file) and 005 (`tests/build-config.test.ts` DoD-8 clause forbade the six TipTap packages); both repaired
- code: done — steps 001, 002, 003, 004, 005, 006, 007, 008 (no re-freeze; no escape valve). Air-gap note: step 006's coder disclosed that a wide `grep -A 80` on `status.md` for its Skeleton entry also surfaced ~40 lines of the `## Tests` inventory (test names and DoD coverage, not test code, and close to a restatement of the DoD list it legitimately reads). It implemented from the spec and never opened a test file. Later dispatches were warned off wide greps. Structural wrinkle for the pipeline: `status.md` holds both the coder-readable `## Skeleton` and the coder-forbidden `## Tests`.
- verify: PASS (run 1) — all eight steps; backend 1808/1808, frontend 2152/2152, no regression outside 009
