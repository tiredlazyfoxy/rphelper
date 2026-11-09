# Feature 010 — setups

| Step | File                              | Status  | Verifier | Date |
|------|-----------------------------------|---------|----------|------|
| 001  | `001.table-error-models.md`       | done    | PASS     | 2026-10-02 |
| 002  | `002.setups-service.md`           | done    | PASS     | 2026-10-02 |
| 003  | `003.setups-router.md`            | done    | PASS     | 2026-10-02 |
| 004  | `004.setups-api-and-state.md`     | done    | PASS     | 2026-10-02 |
| 005  | `005.setup-modal.md`              | done    | PASS     | 2026-10-02 |
| 006  | `006.setups-section.md`           | done    | PASS     | 2026-10-02 |

## Files Changed

### Step 001 — the `setups` table, its not-found error and its pydantic models
- `backend/app/db/schema.py` — verified the `setups` Table literal against D7 and the frozen
  interface (eight columns in order, `id` PK, only `archived_at` nullable, both FKs bare with
  no `ondelete=`, non-unique index on `(user_id, character_id)`, none of the forbidden
  columns, placed after `characters`). Already correct — no change.
- `backend/app/errors.py` — verified `SetupNotFoundError`: `DomainError` subclass, code
  `setup_not_found`, status 404, `detail` empty, placed after `CharacterNotFoundError`.
  Already correct — no change.
- `backend/app/models/setups.py` — verified `SetupName`, `SetupResponse` (seven keys,
  `SnowflakeOut` on `id` **and** `character_id`, no `user_id`), `SetupListResponse`,
  `CreateSetupRequest` and `UpdateSetupRequest` (`extra="ignore"` on the request models only,
  strip-then-non-empty `name`, `description` never stripped and `""` by default on create).
  Already correct — no change.

### Step 002 — the setups service
- `backend/app/services/setups.py` — filled the frozen `Setup` value's six operations and the
  private helpers: every statement carries the owner in its own `WHERE` (or `VALUES`), the parent
  check is this module's own `SELECT characters.id ... WHERE id = :character_id AND user_id = :user_id`
  with no `archived_at` predicate (D5, D6), `list_setups` and `get_setup` read under the `_reading`
  guard so the autobegun transaction ends on the normal return and on the raise, writes run in one
  `with connection.begin():` with the locating read inside it, `create_setup` checks the parent before
  minting the id and stamps `created_at` = `updated_at` from one instant, `update_setup` writes only
  supplied fields and nothing at all when neither is supplied, archive/restore are no-ops on an
  unchanged state (D9) and touch `setups` only (D3), order is `created_at DESC, id DESC` (D10). Added
  the body-only imports (`setups`/`characters` Tables, both not-found errors, `select`, `UTC`/`datetime`,
  `typing.Any`). No removal operation, no `fastapi`, no characters-service import (D6, DoD-12).

### Step 003 — the setups router
- `backend/app/routers/setups.py` — filled the six frozen handler bodies and `_to_response`
  mirroring 009's router: each handler calls its service operation with `current_user.id` as
  `user_id` and returns `_to_response(...)`, which is the single
  `SetupResponse.model_validate(setup, from_attributes=True)` (timestamps handed through as
  text, `user_id` never on the wire). `list_own_setups` passes `include_archived` through and
  wraps the converted rows in `SetupListResponse`; `create_own_setup` passes the injected
  generator plus `body.name` / `body.description` and keeps its 201; `update_own_setup`
  forwards `body.name` / `body.description` as-is, so omitted and explicit `null` are both the
  service's "not supplied" (D5/D8). No `try`/`except` and no status code outside the
  decorators — `SetupNotFoundError` / `CharacterNotFoundError` propagate to `main.py`'s
  registered `DomainError` handler. No SQL, no `DELETE` route, no delete-shaped name. Added
  the body-only service imports by extending the existing `from app.services.setups import`
  line to the six operations, and dropped the now-satisfied "imports to add" note from the
  module docstring (its claim about the import list had become false).
- `backend/app/main.py` — verified only, no change: the `setups_router` import after
  `app.routers.health`, the single `include_router(setups_router)` immediately after the
  characters router's, and the two docstring enumerations are all as frozen.

### Step 004 — the setups API client and the section state
- `frontend/src/app/setupsApi.ts` — filled the five frozen calls and `isSetupArchived` over
  `shared/api`'s `apiGet` / `apiPost` / `apiPatch`, and removed the skeleton's
  `notImplemented`. Private path helpers only: the `/api/setups` constant, a
  `characterSetupsPath(characterId)` and a `setupPath(setupId, suffix = "")`, each
  `encodeURIComponent`-ing the id and never parsing it. `fetchSetups` appends the literal
  `?include_archived=true` by ternary (no `URLSearchParams`) only when the flag is true and
  unwraps `body?.setups ?? []` in the order received; `createSetup` always sends both keys;
  `updateSetup` copies only the supplied keys into its PATCH body; archive/restore POST their
  suffix path with `undefined` as the body. Nothing is caught, so every `ApiError`
  propagates unchanged.
- `frontend/src/app/setupsSectionState.ts` — filled the five frozen free functions and
  removed `notImplemented`; the class is untouched. Added `runInAction`, the value imports
  from `./setupsApi`, a local `isAbortRejection`, the `isVisible` helper and the two fixed
  D12 sentences as module constants. `loadSetups` sets `"loading"` unconditionally, requests
  with `includeArchived` equal to `showArchived`, writes the server's rows with `"ready"`, and
  on failure writes `"failed"` only (rows kept); it checks abort before the write, after the
  `await` and first in the `catch`, and never rejects. `setShowArchived` sets the flag and
  issues no request. `applySetup` is 009 D11's three-case upsert typed to `Setup` (replace in
  place / remove when archived while hidden / insert before the first row whose `created_at`
  is less, else push), always replacing the array via `slice()`. `archiveRow` and
  `restoreRow` are thin wrappers over one private `runRowAction` that clears `error`, sets
  `pendingId`, POSTs, and on success applies the returned row and clears `pendingId` in one
  action; a failure sets its own sentence and clears `pendingId`, leaving the rows unchanged;
  an abort writes nothing. No list refetch follows a mutation.

### Step 005 — the setup draft and the create / edit modal
- `frontend/src/app/setupDraft.ts` — filled the three frozen derivations, the submit effect and
  the two setters, and removed the skeleton's `notImplemented`; the class is untouched. Added
  `runInAction`, the value imports `createSetup` / `updateSetup` from `./setupsApi`, a local
  `isAbortRejection` and the two fixed D12 sentences as module constants. `isEditing` is
  `original !== null`; `isDirty` is true in create mode and compares `name` / `description`
  against the original in edit mode; `canSubmit` requires a non-empty trimmed `name`, no
  in-flight submit and `isDirty`. `submitSetup` guards abort and re-entrancy, snapshots the two
  fields and the mode before the first write, sets `"submitting"` with `error` cleared in one
  action, then POSTs both keys under `draft.characterId` (create) or PATCHes both keys to
  `original.id` (edit, D2); it checks abort after the `await` and first in the `catch`, writes
  only the mode's fixed sentence on failure (typed values kept), returns to `"idle"` in a
  `finally` guarded by `!signal?.aborted`, calls `onSaved` with the server's row as its last
  statement, and never rejects. The name is sent as typed (D8). Both setters write their field
  inside `runInAction`, so the modal never calls it.
- `frontend/src/app/SetupModal.tsx` — filled the frozen `observer` component and removed
  `notImplemented`; the props type is untouched. Mirrors `admin/CreateUserModal.tsx`:
  `useState(() => new SetupDraft(characterId, setup))`, a `useRef<AbortController | null>` and a
  `useEffect(…, [])` whose only job is the unmount abort. Renders `Modal` with bare `opened`,
  `onClose` straight through and `title` `"New setup"` / `"Edit setup"` by `isEditing(draft)`;
  inside, a `form` wrapping a `Stack` whose first child is the bare `<Alert color="red">` holding
  `draft.error` when non-null, then `TextInput` labelled "Name" bound through `setDraftName`, then
  `shared/MarkdownEditor` (unchanged) labelled "Description" bound through `setDraftDescription`
  with `readOnly` while submitting, then "Cancel" (`variant="default"` → `onClose`) and the
  submit "Create" / "Save" with the matching `IconPlus` / `IconDeviceFloppy` left section at the
  repo's main metrics, `disabled` unless `canSubmit(draft)` (read into a local named
  `submitEnabled`, never shadowing the import). Submitting re-checks `canSubmit`, mints a fresh
  controller onto the ref and `void`s `submitSetup(draft, onSaved, controller.signal)`. No
  internal close on success and no notification import.

### Step 006 — the Setups section and its place on the character screen
- `frontend/src/app/SetupsSection.tsx` — filled the frozen `SetupsSection` body and deleted the
  `notImplemented` scaffold. Creates one `SetupsSectionState` with
  `useState(() => new SetupsSectionState(characterId))`; holds `createOpen: boolean` and
  `editTarget: Setup | null` as component-local `useState`; reads `state.showArchived` during
  render and runs 009's `CharacterTree` reload effect on `[state, showArchived]` (fresh
  `AbortController` per run held in a ref, cleanup aborts the previous one, and the switch's
  `onChange` calls `setShowArchived` only). Renders `<section aria-labelledby={useId()}>` with
  `<Title order={3} id=…>Setups</Title>`, the labelled "New setup" `Button` (`IconPlus` at 18 /
  1.5), the `Switch` labelled "Show archived setups", the inline bare `<Alert color="red">` for
  `state.error`, and by status: `<Loader size="sm">`, "Could not load setups" + "Retry"
  (re-running `loadSetups`), the single line "No setups yet." and nothing else, or a
  `<Table striped highlightOnHover>` with one `Table.Tr` per `state.setups` entry in state order
  and **no header row**. Each row: the name `c="dimmed"` when `isSetupArchived` beside a
  `Badge` reading "Archived", then the overflow `Menu` (`position="bottom-end" withinPortal`)
  behind `IconButton` `icon={IconDots}` `sizeVariant="inline"` labelled
  `` `Actions for ${setup.name}` ``, `disabled` while `state.pendingId === setup.id`, wrapped in
  `<Box component="span" display="inline-block">` with the `openedByMenuTarget` no-op click
  (`UsersPage.tsx` precedent, no bare `ActionIcon`); items "Edit" → `setEditTarget(setup)`, then
  "Archive" → `archiveRow` or "Restore" → `restoreRow`, each with its icon as `leftSection` at
  `size={16} stroke={1.5}`, and no confirm. `SetupModal` is mounted only while `createOpen` or
  `editTarget !== null` (`setup={createOpen ? null : editTarget}`); `onSaved` calls
  `applySetup` and then closes, `onClose` only closes. Every effect call is `void`ed; no
  notification import.
- `frontend/src/app/CharacterScreen.tsx` — verified the skeleton's two hunks against the frozen
  record (the `./SetupsSection` import after the `./characterScreenState` block, and the
  `{state.characterId !== null && <SetupsSection key=… characterId=… />}` element between the
  actions `</Group>` and the Sessions-heading comment). Already correct — no change.

## Skeleton

### Step 001 — frozen interface (2026-10-02)

- `backend/app/db/schema.py` — `setups = Table("setups", metadata, …)` — **new**, module-level
  name appended after `characters`, bound to the one `metadata`. Columns in order, verbatim:
  `Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=False)`,
  `Column("user_id", BigInteger().with_variant(Integer(), "sqlite"), ForeignKey("users.id"), nullable=False)`,
  `Column("character_id", BigInteger().with_variant(Integer(), "sqlite"), ForeignKey("characters.id"), nullable=False)`,
  `Column("name", Text, nullable=False)`, `Column("description", Text, nullable=False)`,
  `Column("archived_at", Text, nullable=True)`, `Column("created_at", Text, nullable=False)`,
  `Column("updated_at", Text, nullable=False)`,
  `Index("ix_setups_user_id_character_id", "user_id", "character_id")`.
  Both FKs are bare (no `ondelete=`); the index is **non-unique** and its column list is exactly
  `("user_id", "character_id")`.
- `backend/app/errors.py` — `class SetupNotFoundError(DomainError)` with `code = "setup_not_found"`,
  `http_status = 404`, and
  `def __init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None`
  defaulting `message` to `"That setup does not exist."` — **new**, placed after
  `CharacterNotFoundError` and before `domain_error_handler`. No per-subclass handler
  registration (the base class is already registered).
- `backend/app/models/setups.py` — `SetupName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]`
  — **new** module-level alias; the one stripped/non-empty name type both request models use.
- `backend/app/models/setups.py` — `class SetupResponse(BaseModel)`: `id: SnowflakeOut`,
  `character_id: SnowflakeOut`, `name: str`, `description: str`, `archived_at: str | None`,
  `created_at: str`, `updated_at: str` — **new**; no `model_config`, no `user_id`.
- `backend/app/models/setups.py` — `class SetupListResponse(BaseModel)`: `setups: list[SetupResponse]` — **new**.
- `backend/app/models/setups.py` — `class CreateSetupRequest(BaseModel)`:
  `model_config = ConfigDict(extra="ignore")`, `name: SetupName`, `description: str = ""` — **new**.
- `backend/app/models/setups.py` — `class UpdateSetupRequest(BaseModel)`:
  `model_config = ConfigDict(extra="ignore")`, `name: SetupName | None = None`,
  `description: str | None = None` — **new**; absent and explicit `null` both mean "not supplied"
  (`model_fields_set` is the discriminator).
- Caller-compile edits (out of Source-files scope): None.

### Step 002 — frozen interface (2026-10-02)

All in `backend/app/services/setups.py` (**new file**). Core `Connection` first, `user_id` a
required positional second, no keyword-only parameters, no removal operation.

- `@dataclass(frozen=True) class Setup` — fields in order: `id: int`, `character_id: int`,
  `name: str`, `description: str`, `archived_at: str | None`, `created_at: str`,
  `updated_at: str` — **new**. No `user_id`. Field names and order are exactly
  `SetupResponse`'s seven (step `001`), so `003`'s `model_validate(value, from_attributes=True)`
  stays a one-liner.
- `def list_setups(connection: Connection, user_id: int, character_id: int, include_archived: bool = False) -> list[Setup]`
  — **new**. Raises `CharacterNotFoundError`.
- `def create_setup(connection: Connection, generator: SnowflakeGenerator, user_id: int, character_id: int, name: str, description: str) -> Setup`
  — **new** (parameters one per line in the source). No default for `description`; the request
  model supplies `""`. Raises `CharacterNotFoundError`.
- `def get_setup(connection: Connection, user_id: int, setup_id: int) -> Setup` — **new**.
  Raises `SetupNotFoundError`.
- `def update_setup(connection: Connection, user_id: int, setup_id: int, name: str | None = None, description: str | None = None) -> Setup`
  — **new**. `None` = not supplied. Raises `SetupNotFoundError`.
- `def archive_setup(connection: Connection, user_id: int, setup_id: int) -> Setup` — **new**.
  Raises `SetupNotFoundError`.
- `def restore_setup(connection: Connection, user_id: int, setup_id: int) -> Setup` — **new**.
  Raises `SetupNotFoundError`.

Private, **not frozen** — the coder may reshape or drop any of them. Stubbed so the module's
shape mirrors 009's service: `_setup_select() -> Select[tuple[int, int, str, str, str | None, str, str]]`,
`_to_setup(row: Row[tuple[int, int, str, str, str | None, str, str]]) -> Setup`,
`_owned_update(user_id: int, setup_id: int) -> Update`,
`_require_setup(connection: Connection, user_id: int, setup_id: int) -> Setup`,
`_fetch_existing(connection: Connection, user_id: int, setup_id: int) -> Setup`,
`_require_parent_character(connection: Connection, user_id: int, character_id: int) -> None`,
`@contextmanager _reading(connection: Connection) -> Iterator[None]`, `_now_text() -> str`.

- Every body (public and private) is `raise NotImplementedError`; no SQL, no timestamp, no
  placeholder value is produced.
- Imports in the skeleton are only the ones its signatures use: `Iterator`, `contextmanager`,
  `dataclass`, `Connection, Row, Select, Update` from `sqlalchemy`, and `SnowflakeGenerator`
  from `app.ids`. The bodies' imports (`setups` and `characters` from `app.db.schema`,
  `SetupNotFoundError` and `CharacterNotFoundError` from `app.errors`, `select`, `UTC` /
  `datetime`) are **the coder's to add** — `ruff` `F401` fails an import nothing uses yet.
  This is a lint constraint, not a change to the contract: the parent check stays this
  module's own scoped select (D6), and the characters service is still never imported.
- The source text carries no occurrence of the word `delete` in any case, no `fastapi` and no
  mention of the characters-service module path, not even in a docstring (DoD-12).
- Gates from `backend/`: `mypy app` → clean (44 files), `ruff check .` → clean.
- Caller-compile edits (out of Source-files scope): None — the module has no callers until
  step `003`.

### Step 003 — frozen interface (2026-10-02)

`backend/app/routers/setups.py` (**new file**). **One** router, **no prefix**: the two path
families share nothing longer than `/api`, so every handler carries its full path (D5).

- `router = APIRouter(tags=["setups"], dependencies=[Depends(require_user)])` — **new**.
  Router-level `require_user` covers all six routes (009 D6); no `prefix=`, because
  `prefix="/api/characters"` cannot also serve `/api/setups/...`. Each handler *also* takes
  `CurrentUser` to scope the service call (FastAPI's dependency cache resolves the guard once).
- `def _to_response(setup: Setup) -> SetupResponse` — **new**, private, defined immediately
  after the `router = ...` block and above the first decorator, as 009 places it. Not frozen
  behaviour; the coder fills it with `SetupResponse.model_validate(setup, from_attributes=True)`.
- `@router.get("/api/characters/{character_id}/setups", status_code=200)`
  `def list_own_setups(character_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)], include_archived: bool = False) -> SetupListResponse`
  — **new**. `include_archived` is a bare `bool` with a default and is the **last**
  parameter (no `Query`, no `Annotated`), exactly as `routers/characters.py:80`.
- `@router.post("/api/characters/{character_id}/setups", status_code=201)`
  `def create_own_setup(character_id: SnowflakeIn, body: CreateSetupRequest, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)], generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)]) -> SetupResponse`
  — **new**. **201**; `get_id_generator` imported from `app.routers.bootstrap`, as 009 does.
- `@router.get("/api/setups/{setup_id}", status_code=200)`
  `def read_own_setup(setup_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> SetupResponse`
  — **new**.
- `@router.patch("/api/setups/{setup_id}", status_code=200)`
  `def update_own_setup(setup_id: SnowflakeIn, body: UpdateSetupRequest, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> SetupResponse`
  — **new**.
- `@router.post("/api/setups/{setup_id}/archive", status_code=200)`
  `def archive_own_setup(setup_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> SetupResponse`
  — **new**.
- `@router.post("/api/setups/{setup_id}/restore", status_code=200)`
  `def restore_own_setup(setup_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> SetupResponse`
  — **new**.
- Path ids are the bare inbound alias `SnowflakeIn` (no `Path(...)`), first parameter of every
  handler; every decorator names `status_code` as a bare int literal; no `response_model=`,
  no `responses=`. **No `DELETE` handler and no delete-shaped name anywhere in the module.**
  The router catches nothing: `SetupNotFoundError` / `CharacterNotFoundError` propagate to the
  `DomainError` handler already registered in `app.main`.

`backend/app/main.py` — **changed** (registration only, four hunks):

- `from app.routers.setups import router as setups_router` added after the
  `app.routers.health` import (ruff `I` sorts the router imports alphabetically, so `setups`
  follows `health`; it is the new last router import).
- `app.include_router(setups_router)` added **immediately after**
  `app.include_router(characters_router)` and before `return app` — registration order is
  what keeps 009's routes matching first.
- Module docstring step 5 and `create_app`'s docstring: the router enumeration extended to
  name the characters router (feature `009`) and the setups router (feature `010`). Prose
  only. See `## Notes & Issues` → "Step 003 — main.py docstring enumeration".
- Nothing else: no middleware, no lifespan change, no DDL, no new `build_id_generator` or
  handler registration.

Body-only imports the **coder must add** to `routers/setups.py` (omitted here because ruff
`F401` fails an import nothing uses yet; this is a lint constraint, not a contract change):
the six service operations `list_setups`, `create_setup`, `get_setup`, `update_setup`,
`archive_setup`, `restore_setup`, extending the existing
`from app.services.setups import Setup` line. Everything else the bodies need is already
imported. Every handler body and `_to_response` is `raise NotImplementedError` — no
placeholder response, no SQL, no error translation.

- Gates from `backend/`: `mypy app` → clean (45 source files), `ruff check .` → clean.
  Registration verified without pytest by building `create_app()` and reading its OpenAPI
  schema: the six paths/methods appear with statuses 200/200/201/200/200/200, tag `setups`,
  `include_archived` as a `boolean` query parameter defaulting to `false`, both path ids as
  `integer` path parameters, and 009's four `/api/characters...` paths unchanged.
- Caller-compile edits (out of Source-files scope): None.

### Step 004 — frozen interface (2026-10-02)

`frontend/src/app/setupsApi.ts` (**new file**). Two path families as the wire contract has
them; **no single-setup GET**. Ids are `string` everywhere, never coerced; `ApiError`s
propagate unchanged (the module catches nothing).

- `export type Setup = { id: string; character_id: string; name: string; description: string; archived_at: string | null; created_at: string; updated_at: string }`
  — **new**. Field names, order and types are the wire object verbatim; no renaming layer,
  no `user_id`.
- `export type SetupListResponse = { setups: Setup[] }` — **new** (the listing body).
- `export type CreateSetupInput = { name: string; description: string }` — **new** (both keys
  always sent).
- `export type UpdateSetupPatch = { name?: string; description?: string }` — **new** (exactly
  the supplied keys are sent).
- `export function isSetupArchived(setup: Setup): boolean` — **new**, pure.
- `export async function fetchSetups(characterId: string, includeArchived: boolean, signal?: AbortSignal): Promise<Setup[]>`
  — **new**. `GET /api/characters/<characterId>/setups`, `?include_archived=true` appended
  only when `includeArchived`; resolves to the payload's `setups`, order untouched.
- `export async function createSetup(characterId: string, input: CreateSetupInput, signal?: AbortSignal): Promise<Setup>`
  — **new**. `POST /api/characters/<characterId>/setups`.
- `export async function updateSetup(setupId: string, patch: UpdateSetupPatch, signal?: AbortSignal): Promise<Setup>`
  — **new**. `PATCH /api/setups/<setupId>`.
- `export async function archiveSetup(setupId: string, signal?: AbortSignal): Promise<Setup>` — **new**.
  `POST /api/setups/<setupId>/archive`.
- `export async function restoreSetup(setupId: string, signal?: AbortSignal): Promise<Setup>` — **new**.
  `POST /api/setups/<setupId>/restore`.

`frontend/src/app/setupsSectionState.ts` (**new file**). Data class with observable fields
only — no methods, no computed getters; every effect is a free function taking the state
first.

- `export type SetupsLoadStatus = "idle" | "loading" | "ready" | "failed"` — **new**. The
  literal union is frozen exactly, in this order.
- `export class SetupsSectionState` — **new**. `constructor(characterId: string)` assigns
  `this.characterId = characterId` and then calls
  `makeAutoObservable(this, {}, { autoBind: true })` (009's exact call, empty overrides,
  `autoBind: true`). Fields in declaration order: `characterId: string` (as constructed),
  `setups: Setup[] = []`, `status: SetupsLoadStatus = "idle"`, `showArchived = false`,
  `error: string | null = null`, `pendingId: string | null = null`.
- `export async function loadSetups(state: SetupsSectionState, signal?: AbortSignal): Promise<void>` — **new**.
- `export function setShowArchived(state: SetupsSectionState, showArchived: boolean): void` — **new**.
  (Second parameter named `showArchived`, as `charactersState.ts`'s setter names it; it is
  positional.)
- `export function applySetup(state: SetupsSectionState, setup: Setup): void` — **new**. 009
  D11's three-case upsert, typed to `Setup` / `SetupsSectionState`; `charactersState.ts` is
  not touched or generalised (`004.context.md`).
- `export async function archiveRow(state: SetupsSectionState, setupId: string, signal?: AbortSignal): Promise<void>` — **new**.
- `export async function restoreRow(state: SetupsSectionState, setupId: string, signal?: AbortSignal): Promise<void>` — **new**.

Skeleton scaffolding the **coder must remove**, and what it must add in its place (omitted
here because `noUnusedLocals` / `noUnusedParameters` fail an import or a parameter nothing
reads yet — a compile constraint, not a contract change):

- Both files declare a private `function notImplemented(name: string, ...args: unknown[]): never`
  and every body is `return notImplemented("<name>", …every parameter…)`. Nothing returns a
  placeholder value, builds a path, issues a request or writes to the state. The helper goes
  away once the bodies land; the exported signatures above do not.
- `setupsApi.ts` must gain `import { apiGet, apiPatch, apiPost } from "../shared/api";` and
  the private path helpers (the `/api/setups` constant, a
  `characterSetupsPath(characterId)` and a `setupPath(setupId, suffix = "")`, each
  `encodeURIComponent`-ing the id and never parsing it, per `charactersApi.ts:33-38`).
  Private helpers are **not** frozen — shape them as convenient, but no `URLSearchParams`
  and no id coercion. Archive/restore pass `undefined` as the body.
- `setupsSectionState.ts` must gain `runInAction` from `mobx` (the skeleton imports
  `makeAutoObservable` only), the value imports `fetchSetups`, `archiveSetup`,
  `restoreSetup` and `isSetupArchived` from `./setupsApi` (the skeleton imports only
  `import type { Setup }`), its own
  `isAbortRejection(error) { return error instanceof Error && error.name === "AbortError"; }`,
  the visibility helper, and the two fixed sentences **"Could not archive the setup."** /
  **"Could not restore the setup."** (D12, exact text).

- Gate: `npm run typecheck` from `frontend/` → clean (both projects). `npm test` not run
  (verifier's). No new dependency; no `.js`/`.jsx`/`.mjs`/`.cjs`; relative imports only.
- Caller-compile edits (out of Source-files scope): None — both modules are new and have no
  callers until steps `005` and `006`.

### Step 005 — frozen interface (2026-10-02)

`frontend/src/app/setupDraft.ts` (**new file**). Data class with observable fields only — no
methods, no computed getters; every derivation and effect is a free function taking the draft
first. Shape follows `src/admin/createUserDraft.ts` with the one narrowing `005.context.md`
states: a single `error` string, **not** `serverErrors` / `clientErrors` maps.

- `export type SetupSubmitStatus = "idle" | "submitting"` — **new**. The union is frozen
  exactly, in this order.
- `export class SetupDraft` — **new**.
  `constructor(characterId: string, setup: Setup | null)` assigns `this.characterId`,
  `this.original = setup`, `this.name` / `this.description` (the original's values, or `""`
  when `setup` is null) and then calls `makeAutoObservable(this, {}, { autoBind: true })`
  (step 004's exact call, empty overrides, `autoBind: true`). Fields in declaration order:
  `characterId: string`, `original: Setup | null`, `name: string`, `description: string`,
  `submitStatus: SetupSubmitStatus = "idle"`, `error: string | null = null`.
- `export function isEditing(draft: SetupDraft): boolean` — **new**, pure.
- `export function isDirty(draft: SetupDraft): boolean` — **new**, pure.
- `export function canSubmit(draft: SetupDraft): boolean` — **new**, pure. (Exported under the
  bare name the step file names it; `SetupModal` must not shadow it with a local of the same
  name.)
- `export async function submitSetup(draft: SetupDraft, onSaved: (saved: Setup) => void, signal?: AbortSignal): Promise<void>`
  — **new**. Calls `onSaved` with the **server-returned** `Setup`; it does **not** close the
  modal.
- `export function setDraftName(draft: SetupDraft, value: string): void` — **new**, a MobX
  action (second parameter named `value`, positional).
- `export function setDraftDescription(draft: SetupDraft, value: string): void` — **new**, a
  MobX action.

`frontend/src/app/SetupModal.tsx` (**new file**). One component for both modes; `setup` null is
create, a row is edit. Mounted only while open, so the draft is fresh per open.

- `export type SetupModalProps = { characterId: string; setup: Setup | null; onClose: () => void; onSaved: (saved: Setup) => void }`
  — **new**. Keys, order and types frozen; no `opened`, no `mode` discriminator (the mode is
  `setup === null`).
- `export const SetupModal = observer(function SetupModal(props: SetupModalProps): React.JSX.Element { … })`
  — **new**. A **named** function inside `observer` with the return type annotated, as
  `CreateUserModal.tsx:34-36` declares it. No default export, no `forwardRef`.

**Accessible names — contract (D2, D12).** The JSX is the coder's, these names are not:

- dialog accessible name: the `Modal`'s `title` — **"New setup"** (create) / **"Edit setup"**
  (edit). `Modal` carries bare `opened` for the component's whole lifetime.
- text input labelled **"Name"**, bound to `draft.name` through `setDraftName`.
- `MarkdownEditor` with `label="Description"`, bound to `draft.description` through
  `setDraftDescription`, `readOnly` while `draft.submitStatus === "submitting"`.
- **"Cancel"** button → `onClose` (`variant="default"`, as the precedent).
- submit button **"Create"** (create mode, `leftSection={<IconPlus size={18} stroke={1.5} />}`)
  / **"Save"** (edit mode, `leftSection={<IconDeviceFloppy size={18} stroke={1.5} />}`),
  `disabled` unless `canSubmit(draft)`. Labelled, so `shared/IconButton` does not apply; the
  icon metrics are the "main" pair (`CharacterScreen.tsx:40-42`).
- an inline `Alert` holding `draft.error` when non-null, **above the fields** (first child of
  the `Stack`, as `CreateUserModal.tsx:76-80` places it).
- The modal's own close (X / Escape / overlay) calls `onClose`. **No internal close on
  success**: `submitSetup`'s `onSaved` is the prop `onSaved`, and the parent (step 006) applies
  the row and then unmounts the modal.

Skeleton scaffolding the **coder must remove**, and what it must add in its place (omitted here
because `noUnusedLocals` / `noUnusedParameters` fail an import or a parameter nothing reads yet
— a compile constraint, not a contract change):

- Both files declare a private `function notImplemented(name: string, ...args: unknown[]): never`
  and every body is `return notImplemented("<name>", …every parameter…)`. Nothing returns a
  placeholder value, issues a request, writes to the draft or renders any JSX. `SetupModal`'s
  whole body is that one call, so rendering it throws until the coder fills it.
- `setupDraft.ts` must gain `runInAction` from `mobx` (the skeleton imports
  `makeAutoObservable` only), the value imports `createSetup` and `updateSetup` from
  `./setupsApi` (the skeleton imports only `import type { Setup }`), its own
  `isAbortRejection(error) { return error instanceof Error && error.name === "AbortError"; }`,
  and the two fixed sentences **"Could not create the setup."** / **"Could not save the
  setup."** (D12, exact text). Edit mode PATCHes **both** keys in one call.
- `SetupModal.tsx` must gain `useEffect`, `useRef`, `useState` from `react`, the Mantine
  imports it renders (`Alert`, `Button`, `Group`, `Modal`, `Stack`, `TextInput`), `IconPlus`
  and `IconDeviceFloppy` from `@tabler/icons-react`, `MarkdownEditor` from
  `../shared/MarkdownEditor` (used unchanged), and the value import `SetupDraft` plus the free
  functions from `./setupDraft` (the skeleton imports only `observer`, `React` as a type and
  `import type { Setup }`). Lifecycle mirrors `CreateUserModal.tsx` exactly:
  `const [draft] = useState(() => new SetupDraft(characterId, setup));`, a
  `useRef<AbortController | null>(null)`, and a `useEffect(…, [])` whose only job is the
  cleanup `controllerRef.current?.abort(); controllerRef.current = null;`.

- **No `notifyFailure` and no `@mantine/notifications` import in either file** — 010 adds no
  call site (D12); `tests/conventions.test.ts` guards it.
- Gate: `npm run typecheck` from `frontend/` → clean (both projects). `npm test` not run
  (verifier's). No new dependency; no `.js`/`.jsx`/`.mjs`/`.cjs`; relative imports only (no
  path alias); no `parseInt` and no numeric id anywhere.
- Caller-compile edits (out of Source-files scope): None — both modules are new and have no
  callers until step `006`.

### Step 006 — frozen interface (2026-10-02)

`frontend/src/app/SetupsSection.tsx` (**new file**). One `observer` component; no other
export. It owns one `SetupsSectionState` (004) and the two modal flags, and calls only 004's
free functions.

- `export type SetupsSectionProps = { characterId: string }` — **new**. One key, a string,
  never parsed. No `characters` prop and no state prop: the section creates its own state (D11).
- `export const SetupsSection = observer(function SetupsSection(props: SetupsSectionProps): React.JSX.Element { … })`
  — **new**. A **named** function inside `observer` with the return type annotated, as
  `SetupModal` (005) and `CharacterTree` declare theirs. No default export, no `forwardRef`,
  no props beyond `characterId`.

**Accessible names and texts — contract (D1, D2, D4, D12, D13).** The JSX is the coder's,
these are not:

- the **region**: a `<section>` with `aria-labelledby` pointing at the heading's id, giving
  role `region` with accessible name **"Setups"**. `aria-label` is deliberately not used
  (`006.context.md`); any stable id works (`useId()` or a literal) because nothing asserts the
  id itself. First labelled region in the repo — expected, a plan decision.
- the **heading**: **"Setups"** at `<Title order={3}>` — the same order as the screen's
  "Sessions" heading (`CharacterScreen.tsx`), so the two read as siblings.
- header **button "New setup"**, a labelled `Button` with
  `leftSection={<IconPlus size={18} stroke={1.5} />}`; sets `createOpen` true.
- header **`Switch` labelled "Show archived setups"** (not the tree's "Show archived"),
  `checked={state.showArchived}`, `onChange` calling `setShowArchived(state, checked)` **and
  nothing else** — the reload is the effect's job; calling `loadSetups` here as well would
  double the request.
- by `state.status`: `"idle"` / `"loading"` → a Mantine `Loader`; `"failed"` → the text
  **"Could not load setups"** plus a **"Retry"** button re-running `loadSetups`; `"ready"`
  with no rows → the line **"No setups yet."** and nothing else (no create prompt, R2);
  `"ready"` with rows → a Mantine `Table`, one row per entry of `state.setups`, in state order.
- a **row**: the setup's `name`, `c="dimmed"` when `isSetupArchived(setup)` (the repo's only
  dimming treatment) beside a `Badge` reading exactly **"Archived"**; and a trailing
  `IconButton` — the row's only icon-only control — `icon={IconDots}`, label exactly
  `` `Actions for ${setup.name}` ``, `sizeVariant="inline"`, `disabled` while
  `state.pendingId === setup.id`.
- the **row menu**: a Mantine `Menu`, items **"Edit"** (`IconEdit`, sets `editTarget` to that
  row), then **"Archive"** (`IconArchive`, `archiveRow`) for a working row or **"Restore"**
  (`IconArchiveOff`, `restoreRow`) for an archived one — text labels with the icon as
  `leftSection` at the "inline" metrics `size={16} stroke={1.5}`. **No confirm** on either.
- the **row error**: `state.error`, when non-null, in an inline `Alert` inside the region.
- `SetupModal` (005) mounted **only** while `createOpen` is true (`setup={null}`) or
  `editTarget` is non-null (`setup={editTarget}`); its `onSaved` applies the server's row with
  `applySetup` and then closes, its `onClose` only closes. The flags are component-local
  `useState` — `createOpen: boolean`, `editTarget: Setup | null` — **never MobX**.
- `Menu.Target`: `IconButton` does not forward refs, so it is wrapped in
  `<Box component="span" display="inline-block">` with the documented no-op `onClick`
  (`openedByMenuTarget`), exactly `src/admin/UsersPage.tsx:152-161`. A bare `ActionIcon` is
  forbidden. The trigger's accessible name stays "Actions for <name>".

`frontend/src/app/CharacterScreen.tsx` — **changed** (009-owned file; two hunks, element
insertion only, no signature touched):

- `import { SetupsSection } from "./SetupsSection";` added after the `./characterScreenState`
  import block.
- In the existing-mode `"ready"` return, between the actions `</Group>` and the
  `{/* Heading only; 011 … */}` comment, as a direct child of the `<Stack gap="md">`:

```tsx
        {state.characterId !== null && (
          <SetupsSection key={state.characterId} characterId={state.characterId} />
        )}
```

  Both the `key` and `characterId` are `state.characterId`, the route's string, used verbatim
  — no `parseInt`, no `character.id` fallback. The `!== null` test is a strictness narrowing
  only (`state.characterId` is typed `string | null`; new mode returned far above), **not** a
  behavioural gate: see "Step 006 — the `!== null` narrowing" under `## Notes & Issues`.
  `CharacterScreenProps`, `CharacterScreenState`, `CharacterRouteProps`, `CharacterRoute` and
  every other branch (new mode, loading, not-found, failed) are **unchanged** — none mounts
  the section (D1).

Skeleton scaffolding the **coder must remove**, and what it must add in its place (omitted
here because `noUnusedLocals` / `noUnusedParameters` fail an import or a parameter nothing
reads yet — a compile constraint, not a change to the contract):

- `SetupsSection.tsx` declares a private
  `function notImplemented(name: string, ...args: unknown[]): never` and the whole component
  body is `return notImplemented("SetupsSection", props);`. It renders no JSX, issues no
  request, creates no state and returns no placeholder element, so mounting it throws until
  the coder fills it.
- The skeleton imports only `import type * as React from "react"` and `observer` from
  `mobx-react-lite`. The coder adds: `useEffect`, `useRef`, `useState` (and `useId` if it takes
  that route) from `react`; the Mantine imports it renders (`Alert`, `Badge`, `Box`, `Button`,
  `Group`, `Loader`, `Menu`, `Stack`, `Switch`, `Table`, `Text`, `Title`); `IconArchive`,
  `IconArchiveOff`, `IconDots`, `IconEdit`, `IconPlus` from `@tabler/icons-react`;
  `IconButton` from `../shared/IconButton`; `isSetupArchived` and `import type { Setup }` from
  `./setupsApi`; `SetupsSectionState`, `loadSetups`, `setShowArchived`, `applySetup`,
  `archiveRow`, `restoreRow` from `./setupsSectionState`; and `SetupModal` from
  `./SetupModal`. Relative imports only; no path alias.
- The load effect is 009's `CharacterTree` pattern (`CharacterTree.tsx:68-77`): `showArchived`
  read **during render** so the `observer` re-renders and the effect re-runs, one
  `AbortController` per run held in a ref, and a cleanup that aborts the previous controller.
  Every effect call from a handler is `void`ed (they never reject).
- **No `notifyFailure` and no `@mantine/notifications` import** — 010 adds no call site (D12);
  `tests/conventions.test.ts` guards it.

- Gate: `npm run typecheck` from `frontend/` → clean (both projects). `npm test` not run
  (verifier's). No new dependency; no `.js`/`.jsx`/`.mjs`/`.cjs`; no `parseInt` and no numeric
  id anywhere.
- Caller-compile edits (out of Source-files scope): **None.** `CharacterScreen.tsx` is a
  declared Source file of this step, and nothing else imports `SetupsSection`.
  `characterScreenState.ts`, `CharacterTree.tsx`, `App.tsx`, `charactersState.ts`,
  `charactersApi.ts` and `package.json` were read only and are untouched; no test file was
  created or edited.

## Tests

### Step 001 — tests (2026-10-02)

- `backend/tests/test_setups_models.py` (**new**) — covers DoD-5, DoD-6, DoD-7:
  - DoD-5 (4 tests) — `SetupNotFoundError` is a `DomainError` subclass; `code =
    "setup_not_found"` / `http_status = 404` are set on the subclass; `detail` is `{}`;
    raised from a route on an app with `register_exception_handlers`, the answer is 404 with
    the three-key envelope `{"error": {"code", "message", "detail"}}`, `detail == {}`.
  - DoD-6 (6 tests) — `SetupResponse` serialises `id` **and** `character_id` as decimal
    strings; `archived_at` `None` → JSON `null`; the serialised object is exactly the Wire
    contract's seven keys and never `user_id`; name/description/timestamps pass through;
    `SetupListResponse`'s only key is `setups`, order preserved, empty list.
  - DoD-7 (11 tests incl. two parametrised) — `CreateSetupRequest`: `"  Tavern  "` →
    `"Tavern"`; `""` / `"   "` / missing `name` fail; missing `description` → `""`;
    `"  # Scene\n"` kept exactly; `user_id` / `character_id` / `archived_at` ignored and
    absent from the model. `UpdateSetupRequest`: `{}` with both unset
    (`model_fields_set == set()`); explicit `null` ≡ absent; `" Inn "` → `"Inn"`; blank name
    fails; `description` verbatim (and `""`); unknown keys incl. `character_id` ignored (D5).
- `backend/tests/test_db_schema.py` (**edited**) — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-8:
  - DoD-1 (3 tests) — `setups` in the registry as a `Table` named `setups`;
    `set(tables) - PRE_010_TABLES - LATER_THAN_010_TABLES == NEW_010_TABLES`; every pre-010
    table still registered; the delta survives a table a later feature declares.
  - DoD-2 (5 tests, two parametrised) — exactly the eight columns; `id` alone is the primary
    key; `archived_at` nullable; every other column NOT NULL; none of `model_ref`,
    `system_prompt`, `tools`, `rp_language`, `preferred_language`, `is_default` declared.
  - DoD-3 (3 tests) — `user_id` FK → `users.id`; `character_id` FK → `characters.id`; an
    index whose column list is exactly `["user_id", "character_id"]`, non-unique.
  - DoD-4 (3 tests) — `create_all` on a fresh engine creates `setups` and accepts a row with
    both parents; with `PRAGMA foreign_keys = ON`, a row whose `character_id` names no
    character raises `IntegrityError`, and so does one whose `user_id` names no user.
  - DoD-8 (2 tests + 2 constant edits) — `LATER_THAN_006_TABLES` gained `"setups"` and
    `LATER_THAN_009_TABLES` became `{"setups"}` (one edit each; 006's two deltas share the
    constant), so 006's and 009's existing delta assertions keep their original meaning; two
    new tests re-assert both deltas with `setups` registered. No other assertion changed.
- `backend/tests/test_admin_db_router.py` (**edited**) — covers DoD-9: `UNDECLARED_NAMES`'s
  `"setups"` entry replaced by `"no_such_table"` (a valid identifier no feature's domain will
  ever declare, ending the swap chain), comment rewritten to say so. No test added or changed
  in that file: the existing parametrised
  `test_undeclared_table_name_is_refused_404_with_no_ddl__DoD11` carries the 404
  `unknown_table` coverage over the rescoped list.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
  DoD-9 ✓ (list rescoped; existing `__DoD11` test is its assertion),
  DoD-10 [manual/live, no test].

### Step 002 — tests (2026-10-02)

- `backend/tests/test_setups_service.py` (**new**, 32 test cases incl. parametrisations) —
  file-local `engine` fixture (`create_all`, two users, four raw-inserted characters: two
  of A, one archived of A, one of B), real `SnowflakeGenerator` fixture, `_FixedIdGenerator`
  where a known id matters, `_insert_user` / `_insert_character` raw inserts, and
  `_count_setups` for direct row counts. Covers:
  - DoD-1 (2 tests) — minted id, echoed `character_id` / name / description, `archived_at`
    `None`, `created_at == updated_at`, both fixed-width; `get_setup` equal and the listing
    contains it.
  - DoD-2 (5 cases) — create and list with another user's and with nobody's character id
    raise `CharacterNotFoundError` (parametrised over both ids); the refused create leaves
    the `setups` row count unchanged, on an empty and on a populated table.
  - DoD-3 (2 tests) — create under and list under the user's **archived** character both
    succeed (D5).
  - DoD-4 (2 tests) — two users, three characters: the listing carries only the addressed
    character's rows with and without the flag; a foreign (and archived) setup is absent
    even from the include-archived listing.
  - DoD-5 (2 tests) — default listing `[third, first]` with the middle row archived;
    include-archived `[third, second, first]` (`created_at DESC, id DESC`, D10).
  - DoD-6 (8 cases) — parametrised over `get` / `update` / `archive` / `restore`: another
    user's setup id raises `SetupNotFoundError` and the owner's whole row is unchanged
    afterwards; nobody's id raises the same error.
  - DoD-7 (4 tests) — name only, description only, both, neither; `character_id` and
    `created_at` stand, `updated_at >=` before, no-op returns the identical value, change
    visible through `get_setup`.
  - DoD-8 (2 tests) — archive stamps a fixed-width `archived_at`, row leaves the default
    listing, stays in the include-archived one and is still readable by id; re-archiving
    returns the same `archived_at` **and** the same `updated_at`.
  - DoD-9 (3 tests) — restore nulls `archived_at` and the row returns to the default
    listing; restoring a working setup returns the identical value; updating an archived
    setup succeeds with `archived_at` unchanged.
  - DoD-10 (2 tests) — a raw-inserted character with no `create_setup` call lists empty
    with `include_archived=True` and the table holds zero rows; exercising every other
    operation still leaves zero rows (R2).
  - DoD-11 (3 tests) — `connection.begin()` succeeds after `list_setups`, after
    `get_setup`, and after `list_setups` raised `CharacterNotFoundError`.
  - DoD-12 (2 tests) — source text of `app/services/setups.py`: no `delete(`, no
    case-insensitive `\bdelete\b`, no `fastapi` import (regexes as 009's precedent); and an
    `ast` walk over `Import` / `ImportFrom` finding nothing from `app.services.characters`
    (D6).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
  DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓. No `[manual/live]` item in this step.
- Note for the red gate: the two DoD-12 tests are source-text assertions and so pass
  against the skeleton (the frozen record states the stub already carries no `delete`, no
  `fastapi` and no characters-service path) — as 009's `__DoD11` equivalent did. Every
  other test fails on `NotImplementedError`.

### Step 003 — tests (2026-10-02)

- `backend/tests/test_setups_router.py` (**new**, 31 test cases incl. parametrisations) —
  file-local harness copied from the characters-router pattern (`engine` / `application`
  fixtures, `_insert_user`, `_seed`, `_parse_set_cookie`, `_login_token`, `_as`,
  `_anonymous`, `_player_a`, `_player_b`, `_assert_envelope`), plus setups-specific helpers
  `_collection_path`, `_setup_path`, `_setup_action_path`, `_character`, `_create_setup`,
  `_listing`, `_read_setup`, `_assert_wire_shape`, `_foreign_collection_request`,
  `_foreign_setup_request`. Two roleplayers A and B, each on its own client; characters
  through `POST /api/characters`, setups through the create route; `UNKNOWN_ID` is an id no
  row holds. Covers:
  - DoD-1 (6 cases) — all six routes answer 401 `not_authenticated` anonymously.
  - DoD-2 (3 tests) — create answers 201 with the Wire contract's seven keys, echoed
    name/description, `archived_at` null, fixed-width timestamps, `character_id` equal to
    C's id string; `id` and `character_id` are `str` of decimal digits; the listing contains
    the row and `GET /api/setups/<id>` answers it.
  - DoD-3 (5 cases) — `""` / `"   "` / absent `name` each 422 with the listing unchanged;
    `"  Tavern "` answered and read back as `"Tavern"`; a missing `description` is `""`.
  - DoD-4 (1 test) — a fresh character's `include_archived=true` listing is exactly
    `{"setups": []}`.
  - DoD-5 (5 cases) — GET and POST on another user's character answer 404
    `character_not_found` with `detail == {}`; the refused create leaves the owner's listing
    empty; the foreign-id body equals the nobody's-id body (full body, so `message` too).
  - DoD-6 (8 cases) — GET / PATCH / archive / restore on another user's setup answer 404
    `setup_not_found` with `detail == {}` and leave the owner's row unchanged; each
    foreign-id body equals the nobody's-id body.
  - DoD-7 (2 cases) — A's two characters and B's one: each listing, with and without the
    flag, carries only that character's setups and no foreign row.
  - DoD-8 (4 tests) — name then description PATCH each answer the updated row and both
    persist; a PATCH carrying `character_id` is accepted and ignored (unchanged
    `character_id`, still listed under the origin, absent under the other); `user_id` /
    `archived_at` ignored on create and on patch (not born/left archived, still the
    caller's — 404 for B).
  - DoD-9 (2 tests) — archive answers 200 with a string `archived_at`, the row leaves the
    default listing, stays in the flagged listing and readable by id; archiving again
    answers the same `archived_at`.
  - DoD-10 (1 test) — restore answers 200 with `archived_at` null and the default listing
    contains the row again.
  - DoD-11 (2 tests) — `DELETE /api/setups/<id>` and `DELETE /api/characters/<C>/setups`
    each answer 405 (status only, the existing precedent) and the setup is still returned by
    `GET /api/setups/<id>`.
  - DoD-12 (1 test) — after 009's `POST /api/characters/<C>/archive`, listing C's setups
    answers 200 and creating under C answers 201.
  - DoD-13 (2 cases) — `/api/setups/abc` and `/api/characters/abc/setups` answer 422.
  - DoD-14 (1 test) — `GET /api/characters/<C>` answers the character and
    `POST /api/characters/<C>/archive` answers 200 with this router registered.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
  DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓,
  DoD-15 [manual/live, no test].
- Note for the red gate: three groups pass against the skeleton because they never reach a
  handler body — DoD-1's six 401 cases (router-level `require_user` rejects first), DoD-13's
  two 422 cases (path-id validation precedes dispatch) and DoD-14's one test (009's routes
  are live). Every other test fails on `NotImplementedError`; DoD-11's 405 assertion would
  itself hold, but those tests reach the create route first and so fail red.

### Step 004 — tests (2026-10-02)

- `frontend/tests/app/setupsApi.test.ts` (**new**, 20 tests) — `fetch` stubbed per test with
  `vi.stubGlobal`, real `Response` bodies, `seen(mock)` comparing method/path/search and
  `sentBody(mock)` parsing the serialised body. Covers:
  - DoD-1 (6 tests) — `fetchSetups(CHARACTER_ID, false)` is exactly
    `GET /api/characters/7250000000000000001/setups` with `search === ""`; with `true` exactly
    `?include_archived=true`; resolves to the payload's `setups` unwrapped and in payload
    order; empty listing → `[]`; every `id` **and** `character_id` is the identical string the
    payload carried (both past `MAX_SAFE_INTEGER`, `typeof` asserted); the character id reaches
    the path verbatim.
  - DoD-2 (9 tests) — `createSetup` POSTs the collection path, body exactly
    `{ name, description }` (key set asserted, including `description: ""`); `updateSetup`
    PATCHes `/api/setups/<id>` with the key set `["name"]`, `["description"]`,
    `["description","name"]` and `[]` for an empty patch; `archiveSetup` / `restoreSetup` POST
    `…/archive` / `…/restore`; each resolves to the response's setup; a snowflake id reaches
    every id-addressed route unchanged.
  - DoD-3 (5 tests) — a 404 `setup_not_found` envelope rejects `archiveSetup` with an
    `ApiError` whose `.code` is `setup_not_found` (status 404 too), and likewise `updateSetup`
    / `restoreSetup`; a 404 `character_not_found` rejects the two collection calls with that
    code; `isSetupArchived` true for a string `archived_at`, false for `null`.
- `frontend/tests/app/setupsSectionState.test.ts` (**new**, 37 tests) — `charactersState`'s
  harness (`stubFetch`, `deferred`, `flush` via `setImmediate`, `snapshot` through `toJS`,
  `autorun` observation, a `withSetups(rows, showArchived)` builder writing through
  `runInAction`); ids ascend while `created_at` descends, so any id-based ordering is caught.
  Covers:
  - DoD-4 (1 test) — `new SetupsSectionState("c1")` equals
    `{ characterId: "c1", setups: [], status: "idle", showArchived: false, error: null, pendingId: null }`.
  - DoD-5 (11 tests) — `"loading"` while a held-open request is pending (fresh and reload),
    then `"ready"` with exactly the server's rows in the server's order (including an order
    that is not the `created_at` order), empty listing ready with no rows; no query string
    while `showArchived` is false and `?include_archived=true` while true, both on
    `/api/characters/<characterId>/setups`; an envelope failure and a transport failure each
    write `"failed"`, keep the previous rows and resolve `undefined`; with the signal aborted
    before the response settles (both the rejecting-fetch and the late-success flavours) the
    whole six-field snapshot — `status` included — is unchanged and the promise resolves.
  - DoD-6 (8 tests) — replacement at the same index with the new values (middle row, first
    row, and while `showArchived` is true); insertion by `created_at` descending: newer than
    all lands first, between two lands between them, older than all lands last, the first row
    of an empty list is inserted, and an absent archived row is inserted by `created_at` while
    `showArchived` is true.
  - DoD-7 (6 tests) — archived row while `showArchived` is false removes that id; rows
    unchanged when the id is absent (also when it is newer than everything, and on an empty
    list); while `showArchived` is true it replaces in place and keeps the row, and a restored
    row replaces its archived self in place.
  - DoD-8 (4 tests) — POSTs `/api/setups/<id>/archive`; while pending `pendingId` is that id
    **and** the row is still listed with its pre-action values (never optimistic); after the
    response with `showArchived` false the row is gone and `pendingId` is null; with
    `showArchived` true the row is still listed carrying the response's `archived_at`.
  - DoD-9 (4 tests) — POSTs `/api/setups/<id>/restore`; `pendingId` held while pending and
    cleared after; the row is listed with `archived_at` null; `setShowArchived(state, false)`
    afterwards leaves it listed.
  - DoD-10 (5 tests) — exactly `"Could not archive the setup."` / `"Could not restore the
    setup."`, `setups` unchanged, `pendingId` back to null, promise resolves `undefined`
    (envelope and transport failure); and a row action started after a failure sees
    `state.error === null` **at request time** (recorded inside the `fetch` stub), for a
    following `restoreRow` and for a following `archiveRow`.
  - DoD-11 (5 tests) — `setShowArchived` sets the flag both ways and the `fetch` mock is never
    called, rows and status untouched; an `autorun` reading `setups` re-runs after
    `applySetup` (insert and in-place replace) and one reading `showArchived` re-runs after
    `setShowArchived`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
  DoD-9 ✓, DoD-10 ✓, DoD-11 ✓. No `[manual/live]` item in this step.
- Note for the red gate: **one test is expected green against the skeleton** —
  `setupsSectionState.test.ts`'s single DoD-4 test. The frozen record states the constructor
  really assigns `characterId` and the five field initializers, so the initial-values clause
  holds before any body lands (same situation as step 005's `SetupDraft` constructor note).
  Every other test in both files fails on the stubs' `notImplemented(...)` throw.

### Step 005 — tests (2026-10-02)

- `frontend/tests/app/setupDraft.test.ts` (**new**, 24 tests, no render) — `fetch` stubbed per
  test with `vi.stubGlobal`, a recording `stubBackend` returning `{ mock, calls }`, real
  `Response` bodies, `deferred`/`flush` (via `setImmediate`), a six-field `snapshot(draft)`
  through `toJS`, and a `savedSink()` recording every `onSaved` argument. Every id is a
  decimal string past `MAX_SAFE_INTEGER`; the typed name carries a trailing space, so "the
  name is sent as typed" is observable, and every server response answers a **different**
  name than the typed one, so a re-used typed value would fail. Covers:
  - DoD-1 (11 tests) — a create draft's whole six-field snapshot (`characterId` as
    constructed, `original` null, both strings empty, `"idle"`, `error` null), `isEditing`
    false, `canSubmit` false; `isDirty` true in create mode; `canSubmit` false for `"   "`
    and `"\t\n "` and true for `" T "`; `canSubmit` false while `submitStatus` is
    `"submitting"` and true again at `"idle"`. An edit draft from a setup: the snapshot holds
    that setup's `name` / `description` and the row as `original`, `isEditing` true,
    `isDirty` and `canSubmit` false; a name change and a description change each make both
    true; a cleared name is dirty but not submittable; restoring an edited field to the
    original's value makes `isDirty` false again; `"submitting"` blocks a changed draft too.
  - DoD-2 (4 tests) — exactly one `POST /api/characters/<characterId>/setups` whose body key
    set is `["description","name"]` and whose `name` is the typed string including its
    trailing space; `onSaved` called exactly once with the response's row (and its name is
    not the typed one); `submitStatus` back to `"idle"` with `error` null and the promise
    resolving `undefined`; `"submitting"` while a held-open request is pending, with
    `onSaved` not yet called.
  - DoD-3 (3 tests) — exactly one `PATCH /api/setups/<original id>` with the key set
    `["description","name"]` and both typed values; **both** keys sent even when only the
    description changed (the unchanged `name` travels too, D2); `onSaved` once with the
    response's server-trimmed row, not the typed name.
  - DoD-4 (7 tests) — exactly `"Could not create the setup."` (create) and `"Could not save
    the setup."` (edit), `onSaved` not called, both typed values kept, `"idle"`, promise
    resolves `undefined`; a transport failure reported the same way; a second create and a
    second save started after a failure each observe `draft.error === null` **inside the
    `fetch` stub** (recorded at request time); with the signal aborted before the response
    settles — the rejecting-fetch flavour and the late-success flavour — the whole six-field
    snapshot is unchanged and `onSaved` is never called.
- `frontend/tests/app/SetupModal.test.tsx` (**new**, 9 tests) — renders `SetupModal`
  standalone in `AppProviders` only (no `MemoryRouter`: a setup has no route) through a
  `renderModal(setup)` helper returning `{ onClose, onSaved, view }`; the sanctioned
  `vi.mock("../../src/shared/MarkdownEditor")` textarea stub is copied into this file, so
  "Description" is a plain labelled textarea; the dialog is reached through `screen` and its
  contents through `within(dialog())` (Mantine portal); `userEvent.setup({
  pointerEventsCheck: 0 })`; notifications counted as `.mantine-Notification-root`. Covers:
  - DoD-5 (2 tests) — `setup={null}` renders a dialog whose accessible name is "New setup"
    (and the title text inside it), an empty "Name" textbox, an empty "Description" textbox,
    an enabled "Cancel" and a **disabled** "Create"; typing a name enables "Create" and the
    `fetch` mock is never called.
  - DoD-6 (1 test) — typing both fields and clicking "Create" issues exactly one request,
    a `POST /api/characters/<characterId>/setups` whose body is `{ name, description }` as
    typed; `onSaved` called once with the response's row (a different name than typed); no
    notification rendered.
  - DoD-7 (2 tests) — `setup={TAVERN}` renders a dialog named "Edit setup" whose "Name" and
    "Description" hold that row's values and whose "Save" is disabled; changing the
    description enables "Save", and pressing it issues exactly one
    `PATCH /api/setups/<id>` carrying **both** `name` (unchanged) and `description`, with
    `onSaved` called once with the response's row and no notification.
  - DoD-8 (2 tests) — a 500 on the create and on the save each render the matching sentence
    **inside** the dialog, leave the dialog mounted, leave both typed values in the fields,
    never call `onSaved` and raise no notification.
  - DoD-9 (2 tests) — "Cancel" calls `onClose` exactly once with no request issued and
    `onSaved` untouched; with the response held open, the "Create" button is disabled and the
    Description textarea carries `readonly` while the submit is in flight, and the attribute
    is gone once the response lands.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
  DoD-9 ✓, DoD-10 [manual/live, no test].
- Notes for the red gate:
  - **One test is expected green against the skeleton** — `setupDraft.test.ts`'s
    "starts empty, is not editing and cannot be submitted — DoD-1" would be green on the
    snapshot clause alone, but it also calls `isEditing` and `canSubmit`, which throw, so in
    fact **every** test in both files fails on the stubs' `notImplemented(...)` throw. The
    edit-mode snapshot test is in the same position. No test asserts only constructor state.
  - The **named dialog query** `findByRole("dialog", { name })` is used, as `005.context.md`
    asks, in all nine `SetupModal.test.tsx` tests. It has no precedent in this repo. If it
    does not resolve against the installed Mantine 7 the fault is **TEST**, and the sanctioned
    repair is the unnamed `getByRole("dialog")` plus the title-text assertion that each DoD-5
    / DoD-7 test already carries alongside it.

### Step 006 — tests (2026-10-02)

- `frontend/tests/app/SetupsSection.test.tsx` (**new**, 14 tests) — covers DoD-1..DoD-9.
  Harness copied from 009's precedents (own `vi.mock("../../src/shared/MarkdownEditor")`
  textarea stub, `jsonResponse` / `envelope` / `requestUrl` / `requestMethod` / `parseBody`,
  `flush` via `setImmediate`, `userEvent.setup({ pointerEventsCheck: 0 })`), plus a
  URL-routed in-memory setups backend `serveSetups(rows, failing)` recording every request
  and honouring `?include_archived=true`; its PATCH answers a **different** name
  (`"Stone quarry"`) than the one typed, so a row rendered from the draft would fail.
  Fixtures: one `characterId` and setup ids past `MAX_SAFE_INTEGER`, `created_at`
  descending while ids ascend, no fixture name a substring of another. Every section
  assertion goes through `within(getByRole("region", { name: "Setups" }))`; dialogs and
  menu items through `screen` (Mantine portals); notifications counted as
  `.mantine-Notification-root`.
  - DoD-1 (4 tests) — region + "Setups" heading + "New setup" + an **unchecked** "Show
    archived setups" switch; one row per setup in the payload's order, each showing its
    name; a payload order that is not the `created_at` order is preserved; the mount issues
    **exactly one** request and it is `GET /api/characters/<id>/setups` with an empty search.
  - DoD-2 (2 tests) — "No setups yet." and **no table**; the region's only button is "New
    setup" and its whole text, minus the four contract strings, is empty (no create prompt,
    R2/D13).
  - DoD-3 (2 tests) — a 500 listing renders "Could not load setups" + "Retry" **in the
    region** with no table and **no notification**; "Retry" issues a second listing and the
    rows then render, with the failure text gone.
  - DoD-4 (1 test) — "New setup" opens a dialog titled "New setup"; typing Name and
    Description and pressing "Create" issues exactly one `POST /api/characters/<id>/setups`
    carrying the typed name; afterwards the dialog is gone, the created row is **first**, and
    **no listing request follows the POST** (request log sliced at the POST; total listings
    still 1).
  - DoD-5 (1 test) — the middle row's "Actions for <name>" menu → "Edit" opens a dialog
    titled "Edit setup" with Name and Description **prefilled**; a changed name + "Save"
    issues one `PATCH /api/setups/<id>`; the dialog closes and the row shows the **server's**
    name in the **same (middle) position**, with the old name gone.
  - DoD-6 (2 tests) — a 500 create leaves the dialog mounted with "Could not create the
    setup." **inside it**, the table unchanged and no notification; "Cancel" closes it and
    reopening "New setup" shows an **empty** Name (fresh draft).
  - DoD-7 (1 test) — "Archive" issues one `POST /api/setups/<id>/archive` and the row leaves
    the table; turning the switch on makes the listing searches exactly
    `["", "?include_archived=true"]`, the switch checked, the row back with an "Archived"
    badge **inside its own row**, and its menu offering "Restore" and **not** "Archive";
    `queryByRole("dialog")` is null after every step (**no confirm**).
  - DoD-8 (1 test) — with the switch on, "Restore" issues one `POST /api/setups/<id>/restore`
    and the row loses its "Archived" badge; turning the switch **off** makes the searches
    `["", "?include_archived=true", ""]` and the row is still listed.
  - DoD-9 (1 test) — a 500 archive renders "Could not archive the setup." inside the region,
    the row is still listed, and no notification is raised.
- `frontend/tests/app/CharacterScreen.test.tsx` (**edited**, 009's file) — adds DoD-10,
  DoD-11, DoD-12 and carries half of DoD-13:
  - DoD-10 (4 tests) — at `/characters/<id>` the "Setups" region and its heading are present
    and, by `compareDocumentPosition`, the region **follows** the "Persona" textbox and
    **precedes** the "Sessions" heading; `/characters/new` renders no region (and still
    issues no request at all); the "Character not found" and "Could not load the character"
    states render no region.
  - DoD-11 (1 test) — an archived character shows "Archived" + "Restore" **and** the region;
    "New setup" → dialog → Name → "Create" issues exactly one
    `POST /api/characters/<id>/setups` with the typed name.
  - DoD-12 (1 test) — at `/characters/<a>` the section lists `a`'s setup; the switch is
    turned **on**; the probe navigates to `/characters/<b>`; `b`'s listing is requested
    exactly once with an **empty** search, `b`'s setup shows, `a`'s row is gone and the
    switch is **back off** (D11's keyed reset).
  - **009 assertions amended (none dropped):**
    1. `serveCharacters(...rows)` now also answers `GET /api/characters/<id>/setups` with
       `{ "setups": [] }` for each served row (used by the DoD-8 and DoD-12 tests and
       `renderLoaded`). Its 404 fallback is otherwise unchanged.
    2. The four inline `stubBackend` handlers whose character load succeeds gained one
       URL-routed branch answering the setups listing with `{ "setups": [] }`: the two DoD-3
       create tests (for `CREATED_ID`), the DoD-6 PATCH test, the DoD-7 archive/restore test,
       the DoD-10 Retry test, and the DoD-11 failed-Save test (whose branch sits **above**
       its `serverError()` fallback, so the section never renders its own failure + "Retry"
       inside `main`).
    3. The DoD-5 loader test's handler was rewritten from an expression to a block to add the
       same branch; its `expect(loaders()).toEqual([])` is **unchanged in content** (still
       document-wide, still exactly `[]`) and is now wrapped in `waitFor`, so it waits for the
       section's own `Loader` to go. Nothing was deleted or scoped away.
    4. Everything else in the file is byte-identical: the four `ARCHIVED_BADGE` queries
       (`queryByText` → null, `getByText`, `queryByText` → null, `getByText`), every
       `matching(calls, …)` count, `nameInput()` / `personaInput()`, `button()` /
       `queryButton()`, `notificationsShown()` and the new-mode `expect(calls).toEqual([])` +
       `expect(mock).not.toHaveBeenCalled()` keep their exact text and meaning — an empty
       setups listing renders no row, badge, menu or colliding control, and new mode mounts
       no section at all.
- `frontend/tests/app/App.test.tsx` (**edited**, 009's file) — the other half of DoD-13; no
  test added, no assertion dropped:
  1. `stubWorkspace` gained one URL-routed branch (above its character-id regex) answering
     `GET /api/characters/<id>/setups` with `{ "setups": [] }` when the store holds that
     character, and 404 otherwise — so the section never falls through to the
     `character_not_found` fallback. Used by the DoD-8 create, DoD-9 archive/restore and
     DoD-10 save clauses.
  2. The `/characters/1` DoD-13 clause's `stubFetch` gained the same branch for
     `/api/characters/1/setups`.
  3. `listRequests` is **unchanged** and still keyed on the exact path `/api/characters`, so
     the section's listing is not counted and "no second `GET /api/characters` after a
     create" (009 `008` DoD-8) holds as written.
  4. The `/characters/new` DoD-13 clause is **unchanged** (its stub still rejects every URL
     other than `/api/characters`): new mode mounts no section (D1). `archivedSwitch()` keeps
     its anchored `/^show archived$/i` inside the nav scope — the section's switch is "Show
     archived setups" and is in `main`, so it cannot match. `EMPTY_CENTRE_ROUTES`,
     `mainText()`, `screenControl()`, `screenNameField()`, `treeRowBlock()` and both
     `ARCHIVED_BADGE` tree-row queries are untouched.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
  DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓ (both amended files),
  DoD-14 [manual/live, no test].
- Notes for the red gate:
  - Every new `SetupsSection.test.tsx` test fails on the stub's
    `notImplemented("SetupsSection", …)` throw, as do the new DoD-10..DoD-12 tests.
  - **Expected true-red, not a TEST fault:** 009's existing `CharacterScreen.test.tsx`
    ready-mode tests and `App.test.tsx`'s character-screen clauses now fail with "not
    implemented: SetupsSection", because step 006's skeleton mounts the throwing stub in the
    existing-mode `"ready"` branch (see `## Notes & Issues` → "Step 006 — the ready render
    throws until the coder fills the body"). They are expected green once the body lands.
  - The unnamed `getByRole("dialog")` + a title-text assertion inside it is used instead of
    `getByRole("dialog", { name })`, per step 005's recorded red-gate risk note.

## Notes & Issues

### Step 003 — `main.py` docstring enumeration (skeleton, 2026-10-02)

The step brief states that 009 updated `main.py`'s module-docstring router enumeration when it
registered its router. It did not: on the tree as found, both the module docstring's step 5
(`:19-28`) and `create_app`'s docstring (`:81-83`) stopped at `admin_db_router`, with no mention
of `characters_router` even though `app.include_router(characters_router)` is on `:105`. Taking
the brief's instruction ("extend that prose the same way") at its intent rather than its
premise, the enumeration now names **both** the characters router (feature `009`) and the setups
router (feature `010`) — naming setups alone would have left a list that mentions the later
router but not the one it must follow. This is documentation prose inside a declared Source
file; no behaviour, no code, and no 009 module was touched. Revert the `009` clause if the
owner of `main.py`'s prose prefers the omission kept.

### Step 005 — why `SetupDraft`'s constructor initializes the two fields (skeleton, 2026-10-02)

The skeleton's constructor really does set `name` / `description` from the `setup` argument
instead of throwing. Two reasons, neither of them behaviour: under `strict` a declared field
must be initialized for the class to compile at all, and the obvious alternative (`""` in both
modes) would be exactly the kind of placeholder that can accidentally satisfy a create-mode
assertion. The Interface intent states the initial values as part of the data shape ("the
original's values in edit mode, empty in create mode"), and step 004 froze
`SetupsSectionState`'s `characterId` as-constructed the same way. Everything that is actually
behaviour — `isEditing`, `isDirty`, `canSubmit`, `submitSetup`, both setters and the whole
`SetupModal` body — throws.

### Step 006 — the `!== null` narrowing in `CharacterScreen.tsx` (skeleton, 2026-10-02)

The brief asks for "exactly one new element … `<SetupsSection characterId={…} key={…} />`, both
set to `state.characterId`". That field is typed `string | null`
(`characterScreenState.ts:28`) and TypeScript cannot narrow it at the insertion point: new mode
leaves the component through the early `if (isNewCharacter(state))` return a hundred lines
above, which `strict` does not read as a narrowing of `state.characterId`. The element
therefore sits behind `{state.characterId !== null && (…)}`. The rejected alternatives were
`characterId={state.characterId ?? ""}` (an unreachable branch could then construct a section
with an empty id, which would request `/api/characters//setups`) and
`character === null ? "" : character.id` (a different field than the one the plan names). The
guard's false branch is unreachable in the `"ready"` existing-mode render, and wherever it were
reachable the answer D1 wants is "no section", so it cannot mask a bug. If the owner of this
file prefers a non-null assertion or a narrowed local, it is a one-line swap.

### Step 006 — the ready render throws until the coder fills the body (skeleton, 2026-10-02)

`SetupsSection`'s stub throws when mounted, and `CharacterScreen`'s existing-mode `"ready"`
branch now mounts it. So 009's already-passing assertions on that branch fail at the red gate
with "not implemented: SetupsSection" — not because any 009 behaviour regressed and not because
a test is wrong. A stub that rendered an empty region instead would be exactly the placeholder
the pipeline forbids (it could satisfy a "the Setups region is present" assertion). The
condition clears the moment the coder fills the body; it is not a `TEST` fault.

### Step 006 — `## Skeleton` has a pre-existing nesting glitch (skeleton, 2026-10-02)

Step 005's frozen entry was inserted **inside** step 003's closing sentence (between "See `"
and "`## Notes & Issues` → …", around this file's lines 140 and 235), so the sections read out
of order: 001, 002, 003 (interrupted by 005), 004, 006. Nothing is missing and every entry is
intact. Step 006's entry was appended after 004's rather than re-flowing the file, because
another step's frozen record is not this step's to rewrite.

## Ultra phase

- orient: done 2026-10-02 — 6 steps, 68 `[test]` DoD items, 4 `[manual/live]`; dependency `009.characters` delivered (all rows PASS)
- harvest: done — docs/.cache/ultra/010.setups/harvest.md (4 reports)
- skeleton: done — steps 001, 002, 003, 004, 005, 006 (gates clean at each freeze; `## Skeleton` section order repaired by the orchestrator after 006 — blocks relocated verbatim, no signature changed)
- tests: done — steps 001, 002, 003, 004, 005, 006
- red-gate: PASS (run 1) — all six steps; mypy/ruff/typecheck clean, 68 `[test]` ids traced, 4 `[manual/live]` recorded as requires-live-run
- code: done — steps 001, 002, 003, 004, 005, 006 (no re-freeze; 001 verified complete with no source change, as 009's equivalent step was)
- verify: PASS (run 1) — all six steps; mypy/ruff/typecheck/build clean, backend 1941 passed / 0 failed, frontend 2272 passed / 0 failed, no regression against the red-gate baseline
